"""夹爪抓取状态反馈（SO-101 / Feetech STS3215）

读夹爪电机的 Present_Current 寄存器判定抓取状态：

    EMPTY    : 电流贴近空载基线（空抓或张开着）
    GRASPING : 夹爪闭合指令期间电流持续高于阈值（夹持负载）
    LOST     : 曾 GRASPING，物体脱落 → 电流回落基线但指令仍闭合

设计要点：
    - 双侧滞回：进 GRASPING 需连续 enter_frames 帧超阈值；
      退出（回 EMPTY/判 LOST）需连续 exit_frames 帧低于阈值——
      电流读数有噪声尖刺，单帧翻转会误判。
    - 阈值不自写死：calibrate() 从空载/夹持两段采样自动取
      thr = empty_mean + k*empty_std（k 默认 5），夹持均值
      低于阈值时报警提示换 k 或检查通道。
    - 与闭合指令无关时只报 EMPTY/GRASPING，LOST 需要"指令闭
      合 + 曾抓住 + 电流回落"三条件同时成立，防张开误报。

用法（实机）：
    from grasp_feedback import GraspFeedback, read_gripper_current
    fb = GraspFeedback(thr=calibrated_thr)
    while True:
        cur = read_gripper_current(robot.bus)          # raw 位值
        state = fb.update(cur, cmd_closed=cmd_gripper_close)
        # state in {"EMPTY", "GRASPING", "LOST"}

STS3215 Present_Current 为 12bit 原始寄存器值（约 6.5 mA/LSB，
以 Feetech 手册为准）；本模块全程用原始位值，不换算。
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass

import numpy as np

EMPTY = "EMPTY"
GRASPING = "GRASPING"
LOST = "LOST"


def calibrate(empty_samples: np.ndarray, grasp_samples: np.ndarray,
              k: float = 5.0) -> float:
    """从两段采样自动算阈值：thr = empty_mean + k*empty_std。

    empty_samples: 空载（张开+闭合）下夹爪电流采样
    grasp_samples: 稳定夹持物体时的电流采样（仅用于 sanity check）
    """
    empty = np.asarray(empty_samples, dtype=float).ravel()
    grasp = np.asarray(grasp_samples, dtype=float).ravel()
    if len(empty) < 30:
        raise ValueError("空载样本太少（<30），标定不可靠")
    mu, sd = float(empty.mean()), float(empty.std() + 1e-6)
    thr = mu + k * sd
    if len(grasp) >= 30 and float(grasp.mean()) <= thr:
        raise ValueError(
            f"夹持均值 {grasp.mean():.0f} <= 阈值 {thr:.0f}："
            "电流差不够，检查是否抓稳或换 k 值"
        )
    return thr


@dataclass
class GraspFeedbackConfig:
    thr: float               # 电流阈值（原始位值，calibrate 产出）
    enter_frames: int = 8    # 连续超阈值帧数 → GRASPING（@30Hz≈0.27s）
    exit_frames: int = 10    # 连续低于阈值帧数 → 退出 GRASPING
    lost_frames: int = 10    # 闭合指令下电流回落持续帧数 → LOST


class GraspFeedback:
    """在线抓取状态机。每控制步喂一次电流读数与闭合指令位。"""

    def __init__(self, cfg: GraspFeedbackConfig):
        self.cfg = cfg
        self.reset()

    def reset(self):
        self._above = deque(maxlen=self.cfg.enter_frames)
        self._below = deque(maxlen=max(self.cfg.exit_frames,
                                       self.cfg.lost_frames))
        self._state = EMPTY
        self._was_grasping = False

    @property
    def state(self) -> str:
        return self._state

    def update(self, current_raw: float, cmd_closed: bool) -> str:
        """current_raw: Present_Current 原始位值；cmd_closed: 本步闭合指令。"""
        if not cmd_closed:
            # 张开指令：状态复位为 EMPTY（不判 LOST，防止张开动作误报）
            self._above.clear()
            self._below.clear()
            if self._state == GRASPING:
                self._was_grasping = True   # 松开前的状态留作历史
            self._state = EMPTY
            return self._state

        above = current_raw > self.cfg.thr
        self._above.append(above)
        self._below.append(not above)

        if self._state != GRASPING:
            if (len(self._above) == self.cfg.enter_frames
                    and all(self._above)):
                self._state = GRASPING
                self._was_grasping = True
        else:
            # GRASPING → LOST：指令仍闭合但电流持续回落
            if (self._was_grasping
                    and len(self._below) >= self.cfg.lost_frames
                    and all(list(self._below)[-self.cfg.lost_frames:])):
                self._state = LOST
            elif (len(self._below) == self.cfg.exit_frames
                    and all(self._below) and not self._was_grasping):
                self._state = EMPTY
        return self._state


def read_gripper_current(bus, motor: str = "gripper") -> float:
    """从 lerobot MotorsBus 同步读 Present_Current。

    bus: so_follower / so_leader 的 .bus（FeetechMotorsBus）
    返回原始位值（int）。失败抛异常——调用方决定重试或跳过本帧。
    """
    data = bus.sync_read("Present_Current", [motor])
    return float(data[motor])


# ---------------- 标定采集助手 ----------------

def collect_samples(bus, seconds: float, hz: float = 30.0,
                    motor: str = "gripper") -> np.ndarray:
    """实机采样助手：空载时段先跑一遍得 empty_samples；
    夹稳物体再跑一遍得 grasp_samples，交给 calibrate()。"""
    out = []
    dt = 1.0 / hz
    t_end = time.perf_counter() + seconds
    while time.perf_counter() < t_end:
        t0 = time.perf_counter()
        out.append(read_gripper_current(bus, motor))
        time.sleep(max(0.0, dt - (time.perf_counter() - t0)))
    return np.asarray(out, dtype=float)


if __name__ == "__main__":
    # 离线自检：合成两段电流验证状态机（无机械臂也能跑）
    rng = np.random.default_rng(0)
    cfg = GraspFeedbackConfig(thr=calibrate(
        rng.normal(60, 8, 300), rng.normal(220, 15, 300)))
    fb = GraspFeedback(cfg)
    seq = ([(60, True)] * 20 + [(230, True)] * 30      # 闭合+夹持
           + [(62, True)] * 20)                        # 掉落，指令仍闭合
    for cur, closed in seq:
        fb.update(cur + rng.normal(0, 5), closed)
    assert fb.state == LOST, fb.state
    print("掉落后 state = LOST  ✓")
    for _ in range(10):
        fb.update(60 + rng.normal(0, 5), False)        # 张开复位
    assert fb.state == EMPTY, fb.state
    print("张开后 state = EMPTY ✓")
