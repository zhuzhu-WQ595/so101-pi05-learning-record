"""离线安全监控验证：对已录制的 rollout 轨迹逐帧计算风险分数。

信号（全部来自 observation.state / action，不需真机/FK）：
  1. speed      关节速度 |Δq|*fps（模型指令跳变 = 潜在危险）
  2. accel      关节加速度 |Δ²q|*fps²（抖动信号）
  3. track_err  |action - state|（指令与达成偏差，突增=卡在碰撞/抓空）
  4. limit      关节活动范围越界程度（超出示范集min-max的比例）
  5. gripper    夹爪速度符号振荡频率（反复抓放=抓不住）

风险分数 = 各特征的 z-score（均值/方差用示范集标定）加权线性组合。
用法：
    python offline_risk_check.py \
        --demo /home/pc/.cache/huggingface/lerobot/local/so101_block_stack_clean \
        --rollout /home/pc/.cache/huggingface/lerobot/local/rollout_block_stack_20261110_095742 \
        --out ./monitor_report
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

FPS = 30.0
JOINT_NAMES = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]

# 各特征权重（可调参或后续学习）
WEIGHTS = {"speed": 0.15, "accel": 0.30, "track_err": 0.20, "limit": 0.20, "gripper": 0.15}
GRIPPER_IDX = 5
WINDOW = 15  # 0.5s 滑动窗口


def load_episodes(root: str) -> list[pd.DataFrame]:
    files = sorted(Path(root).glob("data/**/*.parquet"))
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    df = df.sort_values(["episode_index", "frame_index"])
    return [g.reset_index(drop=True) for _, g in df.groupby("episode_index")]


def frame_features(ep: pd.DataFrame) -> dict[str, np.ndarray]:
    """逐帧风险特征，返回 n_frames 长度的特征字典。"""
    state = np.stack(ep["observation.state"].values)  # (n,6)
    action = np.stack(ep["action"].values)

    dstate = np.vstack([np.zeros((1, 6)), np.diff(state, axis=0)]) * FPS
    speed = np.linalg.norm(dstate, axis=1)

    dac = np.vstack([np.zeros((1, 6)), np.diff(dstate, axis=0)])
    accel = np.linalg.norm(dac, axis=1)

    track_err = np.linalg.norm(action - state, axis=1)

    grip_vel = dstate[:, GRIPPER_IDX]
    flips = np.concatenate([[0.0], (np.diff(np.sign(grip_vel)) != 0).astype(float)])
    gripper = np.convolve(flips, np.ones(WINDOW) / WINDOW, mode="same")

    return {"speed": speed, "accel": accel, "track_err": track_err, "state": state, "gripper": gripper}


def calibrate(demo_eps: list[pd.DataFrame]) -> dict:
    """用示范集算各特征的均值/方差和关节活动范围。"""
    feats = [frame_features(e) for e in demo_eps]
    stats = {}
    for k in ("speed", "accel", "track_err", "gripper"):
        v = np.concatenate([f[k] for f in feats])
        stats[k] = {"mean": float(v.mean()), "std": float(v.std() + 1e-6)}
    all_state = np.concatenate([f["state"] for f in feats])
    stats["state_min"] = all_state.min(0)
    stats["state_max"] = all_state.max(0)
    stats["state_range"] = np.maximum(stats["state_max"] - stats["state_min"], 1e-6)
    return stats


def score_episode(ep: pd.DataFrame, cal: dict) -> pd.DataFrame:
    f = frame_features(ep)
    n = len(ep)

    # 越界程度：超出示范集范围的归一化距离
    below = np.maximum(cal["state_min"] - f["state"], 0)
    above = np.maximum(f["state"] - cal["state_max"], 0)
    limit = ((below + above) / cal["state_range"]).max(1)

    z = {}
    for k in ("speed", "accel", "track_err", "gripper"):
        z[k] = np.clip((f[k] - cal[k]["mean"]) / cal[k]["std"], 0, None)
    z["limit"] = np.clip(limit * 5.0, 0, None)  # 越界 20% ≈ z=1

    risk = sum(WEIGHTS[k] * z[k] for k in WEIGHTS)

    return pd.DataFrame({
        "frame": np.arange(n),
        "t": ep["timestamp"].values - ep["timestamp"].iloc[0],
        "risk": risk,
        "speed": f["speed"],
        "accel": f["accel"],
        "track_err": f["track_err"],
        "limit": limit,
        "gripper_osc": f["gripper"],
    })


def danger_windows(scores: pd.DataFrame, thresh: float = 2.0) -> list[dict]:
    """risk>thresh 的连续区间，报告起始时间/时长/峰值。"""
    hot = scores["risk"].values > thresh
    out, start = [], None
    for i, h in enumerate(hot):
        if h and start is None:
            start = i
        elif not h and start is not None:
            seg = scores.iloc[start:i]
            out.append({"t_start": float(seg["t"].iloc[0]), "dur": float(seg["t"].iloc[-1] - seg["t"].iloc[0]),
                        "peak": float(seg["risk"].max())})
            start = None
    if start is not None:
        seg = scores.iloc[start:]
        out.append({"t_start": float(seg["t"].iloc[0]), "dur": float(seg["t"].iloc[-1] - seg["t"].iloc[0]),
                    "peak": float(seg["risk"].max())})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", required=True)
    ap.add_argument("--rollout", required=True)
    ap.add_argument("--out", default="monitor_report")
    ap.add_argument("--thresh", type=float, default=2.0)
    args = ap.parse_args()

    demo_eps = load_episodes(args.demo)
    cal = calibrate(demo_eps)
    print(f"[calibrate] {len(demo_eps)} demo eps  "
          f"speed={cal['speed']['mean']:.2f}±{cal['speed']['std']:.2f}  "
          f"accel={cal['accel']['mean']:.2f}±{cal['accel']['std']:.2f}  "
          f"track={cal['track_err']['mean']:.2f}±{cal['track_err']['std']:.2f}")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    rollout_eps = load_episodes(args.rollout)
    report = {"threshold": args.thresh, "episodes": []}
    for i, ep in enumerate(rollout_eps):
        sc = score_episode(ep, cal)
        dw = danger_windows(sc, args.thresh)
        sc.to_csv(out_dir / f"ep{i:02d}_risk.csv", index=False)
        report["episodes"].append({
            "episode": int(ep["episode_index"].iloc[0]),
            "n_frames": len(ep),
            "risk_mean": float(sc["risk"].mean()),
            "risk_p95": float(sc["risk"].quantile(0.95)),
            "risk_max": float(sc["risk"].max()),
            "danger_windows": dw,
        })
        print(f"[ep{i}] frames={len(ep)} risk_mean={sc['risk'].mean():.2f} "
              f"p95={sc['risk'].quantile(0.95):.2f} max={sc['risk'].max():.2f} "
              f"danger_windows={len(dw)} -> {[ (w['t_start'], round(w['peak'],1)) for w in dw]}")

    # 画每段风险曲线
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        for i, ep in enumerate(rollout_eps):
            sc = pd.read_csv(out_dir / f"ep{i:02d}_risk.csv")
            fig, ax = plt.subplots(figsize=(12, 4))
            ax.plot(sc["t"], sc["risk"], lw=1, label="risk")
            ax.axhline(args.thresh, color="r", ls="--", label=f"thresh={args.thresh}")
            ax.set(xlabel="t (s)", ylabel="risk score", title=f"episode {i} risk timeline")
            ax.legend()
            fig.tight_layout()
            fig.savefig(out_dir / f"ep{i:02d}_risk.png", dpi=110)
            plt.close(fig)
    except ImportError:
        print("matplotlib not installed, skip plots")

    (out_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\n报告输出到 {out_dir}/ (report.json + 每段 CSV/PNG)")


if __name__ == "__main__":
    main()
