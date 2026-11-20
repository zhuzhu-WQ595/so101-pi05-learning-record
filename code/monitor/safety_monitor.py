"""实时监控步（ProcessorStep）：插入 lerobot robot_action_processor 管线，
对每条发往机械臂的动作做风险评分，按三档规则响应。

    NORMAL : risk <= SLOW_THRESH                    放行
    SLOW   : risk >  SLOW_THRESH 持续 SLOW_FRAMES   速度缩放 action=state+k*(action-state)
    BLOCK  : risk >  BLOCK_THRESH 持续 BLOCK_FRAMES 动作冻结为当前状态 + 报警

特征（与离线验证 offline_risk_check.py 一致）：
    speed / accel / track_err / limit(越界) / gripper_osc

标定：构造时传 calibration dict，或调用 calibrate_from_dataset(demo_root)
用示范集在线生成（需 lerobot env，几秒）。
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from lerobot.processor import ProcessorStep
from lerobot.configs.types import PipelineFeatureType, PolicyFeature
from lerobot.lerobot_types import EnvTransition, TransitionKey

logger = logging.getLogger("safety_monitor")

FPS = 30.0
# SO-101 六个 pos 通道名（action_dict / obs_raw 里的 key 前缀）
JOINTS = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]
GRIPPER_IDX = 5
WINDOW = 15  # 0.5s 窗口


@dataclass
class MonitorConfig:
    slow_thresh: float = 2.0     # z-score 加权和阈值（慢速档）
    block_thresh: float = 4.0    # 硬阻断阈值
    # 触发用滑动窗口占比：抖动是脉冲式的，连续帧要求会被互相打断
    slow_window: int = 10        # SLOW 判定窗口长度（帧）
    slow_min_hits: int = 6       # 窗口内 >=N 帧超 slow_thresh → SLOW
    block_window: int = 5        # BLOCK 判定窗口长度
    block_min_hits: int = 2      # 窗口内 >=N 帧超 block_thresh → BLOCK
    slow_gain: float = 0.3       # SLOW 档动作插值系数（0=完全停，1=原速）
    weights: dict = field(default_factory=lambda: {
        "speed": 0.15, "accel": 0.30, "track_err": 0.20, "limit": 0.20, "gripper": 0.15,
    })


def calibrate_from_dataset(demo_root: str) -> dict:
    """从示范 parquet 集在线计算标定统计量（同 offline_risk_check.calibrate）。"""
    files = sorted(Path(demo_root).glob("data/**/*.parquet"))
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)

    state = np.stack(df["observation.state"].values)
    action = np.stack(df["action"].values)

    # 逐 episode 计算以避免 episode 边界造成假速度
    speeds, accels, tracks, oscs = [], [], [], []
    for _, g in df.groupby("episode_index"):
        s = np.stack(g["observation.state"].values)
        a = np.stack(g["action"].values)
        ds = np.vstack([np.zeros((1, s.shape[1])), np.diff(s, axis=0)]) * FPS
        speeds.append(np.linalg.norm(ds, axis=1))
        da = np.vstack([np.zeros((1, s.shape[1])), np.diff(ds, axis=0)])
        accels.append(np.linalg.norm(da, axis=1))
        tracks.append(np.linalg.norm(a - s, axis=1))
        gv = ds[:, GRIPPER_IDX]
        flips = np.concatenate([[0.0], (np.diff(np.sign(gv)) != 0).astype(float)])
        oscs.append(np.convolve(flips, np.ones(WINDOW) / WINDOW, mode="same"))

    def _ms(v):
        v = np.concatenate(v)
        return float(v.mean()), float(v.std() + 1e-6)

    sp_m, sp_s = _ms(speeds)
    ac_m, ac_s = _ms(accels)
    tr_m, tr_s = _ms(tracks)
    os_m, os_s = _ms(oscs)
    return {
        "speed": (sp_m, sp_s), "accel": (ac_m, ac_s),
        "track_err": (tr_m, tr_s), "gripper": (os_m, os_s),
        "state_min": state.min(0), "state_max": state.max(0),
        "state_range": np.maximum(state.max(0) - state.min(0), 1e-6),
    }


class SafetyMonitorStep(ProcessorStep):
    """实时监控步：对 (action, obs) 转换逐帧评分并干预危险动作。"""

    def __init__(self, calibration: dict, config: MonitorConfig | None = None):
        self.cfg = config or MonitorConfig()
        self.cal = calibration
        self.reset()

    # ---------- 内部 ----------

    def _vec(self, d: dict, keys: list[str]) -> np.ndarray:
        return np.array([d.get(f"{j}.pos", np.nan) for j in keys], dtype=float)

    def _risk(self, state: np.ndarray, action: np.ndarray) -> float:
        self._prev_state_buf.append(state)
        self._prev_action_buf.append(action)
        n = len(self._prev_state_buf)
        if n < 2:
            return 0.0

        ds = np.diff(np.array(self._prev_state_buf), axis=0) * FPS          # (n-1,6)
        speed = np.linalg.norm(ds[-1])
        accel = np.linalg.norm(np.diff(ds, axis=0)[-1]) if n >= 3 else 0.0
        track = np.linalg.norm(action - state)

        gv = ds[:, GRIPPER_IDX]
        flips = (np.diff(np.sign(gv)) != 0).astype(float)
        osc = flips[-WINDOW:].mean() if len(flips) else 0.0

        below = np.maximum(self.cal["state_min"] - state, 0)
        above = np.maximum(state - self.cal["state_max"], 0)
        limit = float(((below + above) / self.cal["state_range"]).max())

        def z(x, k):
            m, s = self.cal[k]
            return max(0.0, (x - m) / s)

        risk = (
            self.cfg.weights["speed"] * z(speed, "speed")
            + self.cfg.weights["accel"] * z(accel, "accel")
            + self.cfg.weights["track_err"] * z(track, "track_err")
            + self.cfg.weights["gripper"] * z(osc, "gripper")
            + self.cfg.weights["limit"] * np.clip(limit * 5.0, 0, None)
        )
        return float(risk)

    # ---------- ProcessorStep API ----------

    def __call__(self, transition: EnvTransition) -> EnvTransition:
        action = transition.get(TransitionKey.ACTION)
        obs = transition.get(TransitionKey.OBSERVATION)
        if not isinstance(action, dict) or not isinstance(obs, dict):
            return transition

        state = self._vec(obs, JOINTS)
        act = self._vec(action, JOINTS)
        if np.isnan(state).any() or np.isnan(act).any():
            return transition  # 非 SO-101 动作格式，跳过

        risk = self._risk(state, act)
        self._risk_hist.append(risk)
        self._slow_hits.append(risk > self.cfg.slow_thresh)
        self._block_hits.append(risk > self.cfg.block_thresh)

        slow_alarm = sum(self._slow_hits) >= self.cfg.slow_min_hits
        block_alarm = sum(self._block_hits) >= self.cfg.block_min_hits

        # 响应
        if block_alarm:
            new_act = state.copy()  # 冻结在当前位姿
            if not self._blocked:
                logger.warning("[SAFETY-BLOCK] risk=%.2f, 近%d帧内%d帧>%.1f → 冻结动作",
                               risk, self.cfg.block_window,
                               sum(self._block_hits), self.cfg.block_thresh)
            self._blocked = True
        elif slow_alarm:
            new_act = state + self.cfg.slow_gain * (act - state)
            if not self._slowed:
                logger.info("[SAFETY-SLOW] risk=%.2f, 近%d帧内%d帧>%.1f → 降速至%.0f%%",
                            risk, self.cfg.slow_window,
                            sum(self._slow_hits), self.cfg.slow_thresh,
                            self.cfg.slow_gain * 100)
            self._slowed = True
            self._blocked = False
        else:
            new_act = act
            if self._blocked or self._slowed:
                logger.info("[SAFETY-RELEASE] risk=%.2f 回落，恢复自主", risk)
            self._blocked = self._slowed = False

        # 把干预后的 action 写回 transition（保持 dict 格式）
        new_action = dict(action)
        for j, v in zip(JOINTS, new_act):
            new_action[f"{j}.pos"] = float(v)
        transition[TransitionKey.ACTION] = new_action
        return transition

    def transform_features(
        self, features: dict[PipelineFeatureType, dict[str, PolicyFeature]]
    ) -> dict[PipelineFeatureType, dict[str, PolicyFeature]]:
        return features  # 不改变特征结构

    def get_config(self) -> dict[str, Any]:
        return {
            "slow_thresh": self.cfg.slow_thresh,
            "block_thresh": self.cfg.block_thresh,
            "slow_window": self.cfg.slow_window,
            "slow_min_hits": self.cfg.slow_min_hits,
            "block_window": self.cfg.block_window,
            "block_min_hits": self.cfg.block_min_hits,
            "slow_gain": self.cfg.slow_gain,
        }

    def reset(self) -> None:
        self._prev_state_buf: deque = deque(maxlen=WINDOW + 2)
        self._prev_action_buf: deque = deque(maxlen=WINDOW + 2)
        self._risk_hist: deque = deque(maxlen=WINDOW + 2)
        self._slow_hits: deque = deque(maxlen=self.cfg.slow_window)
        self._block_hits: deque = deque(maxlen=self.cfg.block_window)
        self._slowed = False
        self._blocked = False


# ---------- 工厂：组装带监控的 robot_action_processor ----------

def make_monitored_processors(calibration: dict, config: MonitorConfig | None = None):
    """返回 (teleop_proc, robot_action_proc, robot_obs_proc)，直接喂给
    build_rollout_context(robot_action_processor=...) 使用。"""
    from lerobot.processor import (
        IdentityProcessorStep,
        RobotProcessorPipeline,
        observation_to_transition,
        robot_action_observation_to_transition,
        transition_to_observation,
        transition_to_robot_action,
    )

    teleop = RobotProcessorPipeline(
        steps=[IdentityProcessorStep()],
        to_transition=robot_action_observation_to_transition,
        to_output=transition_to_robot_action,
    )
    robot_action = RobotProcessorPipeline(
        steps=[SafetyMonitorStep(calibration=calibration, config=config)],
        to_transition=robot_action_observation_to_transition,
        to_output=transition_to_robot_action,
    )
    robot_obs = RobotProcessorPipeline(
        steps=[IdentityProcessorStep()],
        to_transition=observation_to_transition,
        to_output=transition_to_observation,
    )
    return teleop, robot_action, robot_obs
