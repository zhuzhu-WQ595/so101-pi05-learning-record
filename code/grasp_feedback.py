"""夹爪抓取状态反馈（SO-101 / Feetech STS3215）

读夹爪电机的 Present_Current 寄存器判定抓取状态：

    EMPTY    : 电流贴近空载基线（空抓或张开着）
    GRASPING : 夹爪闭合指令期间电流持续高于 grip_thr（夹持负载）
    LOST     : 曾 GRASPING，物体脱落 → 电流跌破 lost_thr 但指令仍闭合

实机实测电流区间（mA，SO-101 夹爪电机）：
    空载静止        : 10 – 20
    空载开合运动    : 80 – 180   ← 开合动作本身会引起电流波动
    常规夹持        : 250 – 600
    用力夹紧        : 800 – 1000

设计要点：
    - 双阈值滞回（不是单阈值）：进 GRASPING 用 grip_thr=350mA
      （初始建议区间 300–400），判掉落/空抓用更低的 lost_thr=200mA。
      中间 200–350 为保持带——因为空载开合运动可到 180mA，
      若进出共用一个阈值，运动尖峰会贴着阈值反复翻转；
      若 lost_thr 设得太高，又会把弱夹持（250mA 档）误判掉落。
    - 帧数防抖：进 GRASPING 需连续 enter_frames 帧超 grip_thr；
      判 LOST 需连续 lost_frames 帧低于 lost_thr。
    - 阈值可用 calibrate() 从实机采样自动算，也可直接用上面的
      实测区间手填。
    - LOST 需要「指令闭合 + 曾抓住 + 电流回落」三条件同时成立，
      张开指令直接复位 EMPTY，防张开动作误报。

用法（实机）：
    from grasp_feedback import GraspFeedback, read_gripper_current_ma
    fb = GraspFeedback()                    # 用实测默认阈值
    while True:
        cur_ma = read_gripper_current_ma(robot.bus)
        state = fb.update(cur_ma, cmd_closed=cmd_gripper_close)
        # state in {"EMPTY", "GRASPING", "LOST"}

STS3215 Present_Current 为原始寄存器值（约 6.5 mA/LSB，以
Feetech 手册为准）；上层接口全部用 mA，raw→mA 用 ma_per_lsb 换算。
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

EMPTY = "EMPTY"
GRASPING = "GRASPING"
LOST = "LOST"

MA_PER_LSB = 6.5  # STS3215 Present_Current 原始位值 → mA（以手册为准）


def raw_to_ma(raw: float, ma_per_lsb: float = MA_PER_LSB) -> float:
    """寄存器原始位值 → mA。"""
    return float(raw) * ma_per_lsb


def calibrate(empty_samples: np.ndarray, grasp_samples: np.ndarray,
              k: float = 5.0) -> tuple[float, float]:
    """从两段采样（mA）自动算双阈值 → (grip_thr, lost_thr)。

    empty_samples: 空载采样，**要覆盖静止和开合运动两段**——运动尖峰
                   （实测可到 180mA）必须落在 lost_thr 之下才会被
                   empty.max() 项兜住。
    grasp_samples: 稳定夹持物体的电流采样（仅用于 sanity check）

    grip_thr = max(empty_mean + k*empty_std, empty.max() + 20)
    lost_thr = grip_thr * 0.6（经验值，须低于最弱夹持档位 250mA）
    """
    empty = np.asarray(empty_samples, dtype=float).ravel()
    grasp = np.asarray(grasp_samples, dtype=float).ravel()
    if len(empty) < 30:
        raise ValueError("空载样本太少（<30），标定不可靠")
    mu, sd = float(empty.mean()), float(empty.std() + 1e-6)
    grip_thr = max(mu + k * sd, float(empty.max()) + 20.0)
    if len(grasp) >= 30 and float(grasp.mean()) <= grip_thr:
        raise ValueError(
            f"夹持均值 {grasp.mean():.0f} <= grip_thr {grip_thr:.0f}："
            "电流差不够，检查是否抓稳或换 k 值"
        )
    return grip_thr, grip_thr * 0.6


@dataclass
class GraspFeedbackConfig:
    grip_thr: float = 350.0  # 进 GRASPING 阈值 mA（实测建议 300–400）
    lost_thr: float = 200.0  # 判 LOST/退出阈值 mA（须 > 空载运动峰值 ~180，
                             #   < 最弱夹持档 ~250）
    enter_frames: int = 8    # 连续超 grip_thr 帧数 → GRASPING（@30Hz≈0.27s）
    lost_frames: int = 10    # 连续低于 lost_thr 帧数 → LOST
    ma_per_lsb: float = MA_PER_LSB  # raw→mA 换算系数


class GraspFeedback:
    """在线抓取状态机。每控制步喂一次电流读数与闭合指令位。"""

    def __init__(self, cfg: GraspFeedbackConfig | None = None):
        self.cfg = cfg or GraspFeedbackConfig()
        self.reset()

    def reset(self):
        self._n_above = 0     # 连续 ≥grip_thr 帧数
        self._n_below = 0     # 连续 ≤lost_thr 帧数
        self._state = EMPTY

    @property
    def state(self) -> str:
        return self._state

    def update(self, current_ma: float, cmd_closed: bool) -> str:
        """current_ma: 夹爪电流 mA；cmd_closed: 本步闭合指令。"""
        if not cmd_closed:
            # 张开指令：复位 EMPTY（不判 LOST，防张开动作误报）
            self._n_above = self._n_below = 0
            self._state = EMPTY
            return self._state

        if current_ma >= self.cfg.grip_thr:
            self._n_above += 1
            self._n_below = 0
        elif current_ma <= self.cfg.lost_thr:
            self._n_below += 1
            self._n_above = 0
        # else: 落在 200–350 保持带，计数不变——运动尖峰/弱夹持不翻转

        if self._state != GRASPING:
            if self._n_above >= self.cfg.enter_frames:
                self._state = GRASPING
        elif self._n_below >= self.cfg.lost_frames:
            # GRASPING → LOST：指令仍闭合但电流持续跌破下阈值
            self._state = LOST
        return self._state

    def update_raw(self, current_raw: float, cmd_closed: bool) -> str:
        """喂原始位值的便捷入口。"""
        return self.update(raw_to_ma(current_raw, self.cfg.ma_per_lsb),
                           cmd_closed)


def read_gripper_current(bus, motor: str = "gripper") -> float:
    """从 lerobot MotorsBus 同步读 Present_Current，返回原始位值。

    bus: so_follower / so_leader 的 .bus（FeetechMotorsBus）
    失败抛异常——调用方决定重试或跳过本帧。
    """
    data = bus.sync_read("Present_Current", [motor])
    return float(data[motor])


def read_gripper_current_ma(bus, motor: str = "gripper",
                            ma_per_lsb: float = MA_PER_LSB) -> float:
    """读 Present_Current 并换算成 mA。"""
    return raw_to_ma(read_gripper_current(bus, motor), ma_per_lsb)


# ---------------- 标定采集助手 ----------------

def collect_samples(bus, seconds: float, hz: float = 30.0,
                    motor: str = "gripper") -> np.ndarray:
    """实机采样助手（返回 mA）：
    空载采样要跑两段——静止 + 开合运动各几秒，合并成 empty_samples
    （运动尖峰必须被采到，否则标出的阈值会被运动电流误触）；
    再夹稳物体采 grasp_samples，交给 calibrate()。"""
    out = []
    dt = 1.0 / hz
    t_end = time.perf_counter() + seconds
    while time.perf_counter() < t_end:
        t0 = time.perf_counter()
        out.append(read_gripper_current_ma(bus, motor))
        time.sleep(max(0.0, dt - (time.perf_counter() - t0)))
    return np.asarray(out, dtype=float)


if __name__ == "__main__":
    # 离线自检：按实测区间合成电流验证状态机（无机械臂也能跑）
    rng = np.random.default_rng(0)
    fb = GraspFeedback()   # 默认 grip_thr=350mA, lost_thr=200mA

    # 1) 空载闭合指令 + 开合运动尖峰（180mA）→ 应始终 EMPTY
    for _ in range(30):
        fb.update(rng.uniform(10, 20), True)      # 静止段
        fb.update(rng.uniform(80, 180), True)     # 运动尖峰
    assert fb.state == EMPTY, fb.state
    print("空载运动尖峰不误判 → EMPTY ✓")

    # 2) 夹持 400mA 持续 → GRASPING
    for _ in range(20):
        fb.update(rng.normal(400, 40), True)
    assert fb.state == GRASPING, fb.state
    print("夹持 → GRASPING ✓")

    # 3) 夹持中短暂落进保持带（300mA，2 帧）→ 仍 GRASPING
    for _ in range(2):
        fb.update(300, True)
    assert fb.state == GRASPING, fb.state
    print("保持带不翻转 → GRASPING ✓")

    # 4) 掉落：指令仍闭合，电流回落空载基线 → LOST
    for _ in range(15):
        fb.update(rng.normal(15, 5), True)
    assert fb.state == LOST, fb.state
    print("掉落后 state = LOST ✓")

    # 5) 张开复位 → EMPTY
    for _ in range(5):
        fb.update(15, False)
    assert fb.state == EMPTY, fb.state
    print("张开后 state = EMPTY ✓")
