"""抓取失败重试编排（LOST → 回抓取前位姿 → 交还策略重抓）

配合 grasp_feedback.py 使用：状态机判出 LOST 后，本模块接管动作流：

    FOLLOW    : 正常透传策略动作；在「闭合指令上升沿」快照抓取前位姿
    RETURNING : 检测到 LOST → 丢弃策略输出，线性插值回抓取前位姿，
                夹爪通道保持张开（若残留半夹状态先放开）
    RESUME    : 回位完成后把控制权交还策略（模型有 DAgger 恢复数据，
                会自己重新对准抓取）；GRASPING → 回 FOLLOW，
                resume_steps 超时没抓住 → 计一次重试重新 RETURNING。
                注意 RESUME 期间反馈仍停在 LOST 是预期的——掉落刚发生、
                状态要等张开+重夹才会翻走，不能把残留 LOST 当新失败。
    EXHAUSTED : 重试次数超限 → 冻结在当前位姿等人工处理

设计要点：
    - SO-101 是绝对位置动作，「回位」= 往快照位姿做线性插值，
      不存在置零/速度模式问题。
    - 回位期间每帧丢弃策略动作——等效于这段时间清空动作队列
      （策略 chunk 队列在 processor 上游清不掉，但下游丢弃同效）。
    - 编排器本体不碰硬件：current_ma / state / fb_state 都是入参，
      可离线单测；GraspRetryStep 适配层注入 current_getter 读总线。

用法（rollout 管线）：
    bus_holder = {"bus": None}                      # 懒绑定
    steps = [GraspRetryStep(feedback_cfg, retry_cfg,
                            current_getter=lambda: read_gripper_current_ma(bus_holder["bus"])),
             SafetyMonitorStep(calibration=cal)]
    ctx = build_rollout_context(...)
    bus_holder["bus"] = ctx.robot.bus               # ctx 建好后回填
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from grasp_feedback import EMPTY, GRASPING, LOST, GraspFeedback, GraspFeedbackConfig

logger = logging.getLogger("grasp_retry")

FOLLOW, RETURNING, SETTLE, RESUME, EXHAUSTED = (
    "FOLLOW", "RETURNING", "SETTLE", "RESUME", "EXHAUSTED")

JOINTS = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]
GRIPPER_IDX = 5
# SO-101 夹爪指令：归一化值越小越闭合（实标：15=微张、30+=充分张开、~0=闭合）
GRIPPER_OPEN = 40.0     # 编排期间夹爪保持的张开值
GRIPPER_CLOSE = 0.0     # 闭合指令值


@dataclass
class RetryConfig:
    return_steps: int = 60     # 回位插值步数（@30Hz ≈ 2s）
    settle_steps: int = 15     # 回位后稳定步数再交还（≈0.5s）
    resume_steps: int = 150    # 交还策略的观察窗口（≈5s 内看能否重新夹住）
    max_retries: int = 2       # 每次抓取任务允许的重试次数
    grip_close_thresh: float = 15.0  # 指令 ≤ 此值视为 cmd_closed


@dataclass
class GraspRetryOrchestrator:
    """纯逻辑编排器：每控制步喂 (策略动作, 当前观测, 反馈状态)，出下发动作。"""

    cfg: RetryConfig = field(default_factory=RetryConfig)

    def __post_init__(self):
        self.reset()

    def reset(self):
        self.phase = FOLLOW
        self.retries = 0
        self._pre_grasp: np.ndarray | None = None  # 快照的抓取前位姿
        self._interp: np.ndarray | None = None     # 回位插值轨迹
        self._t = 0
        self._prev_cmd_closed = False

    @property
    def exhausted(self) -> bool:
        return self.phase == EXHAUSTED

    def _snapshot_on_close_edge(self, action: np.ndarray, state: np.ndarray,
                                cmd_closed: bool):
        """闭合指令上升沿：此刻臂还没动，位姿 = 抓取前悬停位。"""
        if cmd_closed and not self._prev_cmd_closed:
            self._pre_grasp = state.copy()
        self._prev_cmd_closed = cmd_closed

    def _start_return(self, state: np.ndarray):
        self.phase = RETURNING
        self._t = 0
        if self._pre_grasp is None:
            # 没有快照（比如一上电就 LOST）：退化为原地张开→交还
            self._pre_grasp = state.copy()
        n = self.cfg.return_steps
        self._interp = np.linspace(state, self._pre_grasp, n + 1)[1:]  # 末帧=目标

    def step(self, action: np.ndarray, state: np.ndarray,
             fb_state: str) -> tuple[np.ndarray, str]:
        """返回 (下发动作 6 维, 阶段名)。action/state 均为归一化位姿向量。"""
        cmd_closed = action[GRIPPER_IDX] <= self.cfg.grip_close_thresh
        out = action.copy()

        if self.phase == FOLLOW:
            self._snapshot_on_close_edge(action, state, cmd_closed)
            if fb_state == LOST:
                if self.retries >= self.cfg.max_retries:
                    self.phase = EXHAUSTED
                    logger.warning("[RETRY-EXHAUSTED] 重试 %d 次仍掉落，冻结等人工",
                                   self.retries)
                else:
                    self.retries += 1
                    self._start_return(state)
                    logger.info("[RETRY-%d] LOST → 回抓取前位姿", self.retries)

        if self.phase == RETURNING:
            out = self._interp[self._t].copy()
            out[GRIPPER_IDX] = GRIPPER_OPEN   # 回位期间保持张开
            self._t += 1
            if self._t >= len(self._interp):
                self.phase = SETTLE
                self._t = 0
            return out, self.phase

        if self.phase == SETTLE:
            out = self._pre_grasp.copy()
            out[GRIPPER_IDX] = GRIPPER_OPEN
            self._t += 1
            if self._t >= self.cfg.settle_steps:
                self.phase = RESUME
                self._t = 0
                logger.info("[RETRY] 回位完成，交还策略")
            return out, self.phase

        if self.phase == RESUME:
            self._snapshot_on_close_edge(action, state, cmd_closed)
            self._t += 1
            if fb_state == GRASPING:
                self.phase = FOLLOW      # 重抓成功，本轮 retries 清零
                self.retries = 0
                logger.info("[RETRY] 重抓成功 → FOLLOW")
            elif self._t >= self.cfg.resume_steps:
                # 超时没抓住才计重试；RESUME 中残留的 LOST 不算新失败
                if self.retries >= self.cfg.max_retries:
                    self.phase = EXHAUSTED
                    logger.warning("[RETRY-EXHAUSTED] 重试 %d 次仍失败，冻结", self.retries)
                else:
                    self.retries += 1
                    self._start_return(state)
                    logger.info("[RETRY-%d] 超时未抓住，再试", self.retries)
            return out, self.phase

        if self.phase == EXHAUSTED:
            out = state.copy()           # 冻结在当前位姿
            out[GRIPPER_IDX] = GRIPPER_OPEN
            return out, self.phase

        return out, self.phase


class GraspRetryStep:
    """robot_action_processor 适配层：内部含 GraspFeedback + Orchestrator。

    current_getter: 无参回调返回夹爪电流 mA——总线在 build_rollout_context
    之后才有，用懒绑定 holder 传入。
    """

    def __init__(self, feedback_cfg: GraspFeedbackConfig | None = None,
                 retry_cfg: RetryConfig | None = None,
                 current_getter: Callable[[], float] | None = None):
        self.fb = GraspFeedback(feedback_cfg)
        self.orch = GraspRetryOrchestrator(retry_cfg or RetryConfig())
        self._get_current = current_getter

    def _vec(self, d: dict) -> np.ndarray:
        return np.array([d.get(f"{j}.pos", np.nan) for j in JOINTS], dtype=float)

    def __call__(self, transition):
        from lerobot.lerobot_types import TransitionKey
        action = transition.get(TransitionKey.ACTION)
        obs = transition.get(TransitionKey.OBSERVATION)
        if not isinstance(action, dict) or not isinstance(obs, dict) \
                or self._get_current is None:
            return transition
        act = self._vec(action)
        state = self._vec(obs)
        if np.isnan(state).any() or np.isnan(act).any():
            return transition

        cmd_closed = act[GRIPPER_IDX] <= self.orch.cfg.grip_close_thresh
        try:
            cur_ma = self._get_current()
        except Exception as exc:                     # 读电流失败不阻断控制
            logger.warning("gripper current read failed: %s", exc)
            cur_ma = 0.0
        fb_state = self.fb.update(cur_ma, cmd_closed)

        new_act, phase = self.orch.step(act, state, fb_state)
        if phase != FOLLOW or not np.allclose(new_act, act):
            new_action = dict(action)
            for j, v in zip(JOINTS, new_act):
                new_action[f"{j}.pos"] = float(v)
            transition[TransitionKey.ACTION] = new_action
        return transition

    def transform_features(self, features):
        return features

    def get_config(self) -> dict:
        c = self.orch.cfg
        return {"return_steps": c.return_steps, "settle_steps": c.settle_steps,
                "resume_steps": c.resume_steps, "max_retries": c.max_retries}

    def reset(self):
        self.fb.reset()
        self.orch.reset()


if __name__ == "__main__":
    # 离线自检：模拟一次掉落→回位→交还→重抓/再掉→EXHAUSTED
    rng = np.random.default_rng(0)
    orch = GraspRetryOrchestrator(RetryConfig(return_steps=8, settle_steps=2,
                                            resume_steps=8, max_retries=1))
    fb = GraspFeedback()

    def fake_current(grasping: bool) -> float:
        return rng.normal(400, 30) if grasping else rng.normal(15, 5)

    state = np.array([10, 20, 30, 40, 50, 40.0])     # 悬停位，夹爪张开
    seen = set()

    # 1) 闭合指令→空载基线→夹住（GRASPING）
    cmd = state.copy(); cmd[GRIPPER_IDX] = GRIPPER_CLOSE
    for _ in range(15):
        fb.update(fake_current(False), True)
        _, ph = orch.step(cmd, state, fb.state); seen.add(ph)
    for _ in range(12):
        fb.update(fake_current(True), True)
        orch.step(cmd, state, fb.state)
    assert fb.state == GRASPING and orch.phase == FOLLOW
    pre_grasp = orch._pre_grasp.copy()

    # 2) 搬运中掉落（位置变了、电流回落）→ LOST → RETURNING
    state2 = pre_grasp + np.array([0, -15, 10, 0, 0, 0])
    for _ in range(12):
        fb.update(fake_current(False), True)
        out, ph = orch.step(cmd, state2, fb.state); seen.add(ph)
    assert fb.state == LOST and orch.phase in (RETURNING, "SETTLE", RESUME)
    assert out[GRIPPER_IDX] == GRIPPER_OPEN          # 回位期间张开
    print("掉落 → RETURNING ✓  插值目标=抓取前位姿",
          np.allclose(orch._interp[-1][:5], pre_grasp[:5]))

    # 3) 回位+稳定→RESUME：策略重新闭合又夹住 → GRASPING → 回 FOLLOW，retries 清零
    cmd2 = pre_grasp.copy(); cmd2[GRIPPER_IDX] = GRIPPER_CLOSE
    for _ in range(20):
        fb.update(fake_current(True), True)           # 交还期间重新夹住
        out, ph = orch.step(cmd2, pre_grasp, fb.state); seen.add(ph)
    assert orch.phase == FOLLOW and orch.retries == 0, (orch.phase, orch.retries)
    print("重抓成功 → FOLLOW, retries 清零 ✓")

    # 4) 再掉一次→回位→交还超时仍没抓住（max_retries=1）→ EXHAUSTED 冻结
    for i in range(4):
        for _ in range(15):
            fb.update(fake_current(False), True)
            out, ph = orch.step(cmd2, state2, fb.state); seen.add(ph)
    assert orch.phase == EXHAUSTED
    assert np.allclose(out[:5], state2[:5])          # 冻结在当前位姿
    print("耗尽重试 → EXHAUSTED 冻结 ✓  路径:", "→".join(sorted(seen)))
