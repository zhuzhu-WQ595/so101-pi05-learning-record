#!/usr/bin/env python3
"""RL Token 章节配图：pipeline 示意、关键阶段时间线、训练曲线（示意）。
输出到 ../images/，供 make_docx.py 的 figure() 引用。
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

plt.rcParams["font.sans-serif"] = ["Noto Sans CJK SC", "Droid Sans Fallback", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

IMG = Path(__file__).resolve().parent.parent / "images"

C_VLA = "#4C72B0"
C_ACT = "#DD8452"
C_CRIT = "#55A868"
C_GRAY = "#8C8C8C"


def box(ax, xy, w, h, text, fc, fs=11, tc="white"):
    b = FancyBboxPatch(xy, w, h, boxstyle="round,pad=0.06",
                       linewidth=0, facecolor=fc, zorder=2)
    ax.add_patch(b)
    ax.text(xy[0] + w / 2, xy[1] + h / 2, text, ha="center", va="center",
            fontsize=fs, color=tc, zorder=3)


def arrow(ax, p1, p2, color=C_GRAY, style="-|>", lw=1.8, ls="-", shrink=0):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle=style, mutation_scale=14,
                                 linewidth=lw, color=color, linestyle=ls,
                                 shrinkA=shrink, shrinkB=shrink, zorder=1))


# ---------------- fig 1: pipeline ----------------
fig, ax = plt.subplots(figsize=(12.5, 5.4))
ax.set_xlim(0, 125); ax.set_ylim(0, 54); ax.axis("off")

box(ax, (2, 30), 20, 9, "冻结 π0.5（VLA）", C_VLA)
box(ax, (27, 30), 20, 9, "prefix 表征\n（离线预计算 mmap）", C_VLA, fs=10)
box(ax, (52, 30), 20, 9, "RLT encoder/decoder\n（Stage 1 训练）", C_VLA, fs=10)
box(ax, (77, 30), 14, 9, "z_rl\n2048 维", C_VLA, fs=10)

box(ax, (2, 6), 20, 9, "示范数据集\n+ 关键阶段标注", "#6C8EBF", fs=10)
box(ax, (27, 6), 20, 9, "关键阶段判定\n（手按 c / 分类器）", C_ACT, fs=10)
box(ax, (52, 6), 20, 9, "Actor\n（接管关键阶段）", C_ACT)
box(ax, (77, 6), 14, 9, "动作\nchunk", C_ACT, fs=10)
box(ax, (97, 18), 16, 9, "SO-101\n实机执行", "#7A5195", fs=10)
box(ax, (52, 18), 20, 7.5, "replay buffer\n（只存关键阶段）", C_GRAY, fs=9)
box(ax, (97, 6), 16, 7.5, "y / n\n人工奖励", C_CRIT, fs=10)
box(ax, (27, 42.5), 40, 7.5, "Critic 后台异步更新（不阻塞 50Hz 控制）", C_CRIT, fs=10)

arrow(ax, (22, 34.5), (27, 34.5), C_VLA)
arrow(ax, (47, 34.5), (52, 34.5), C_VLA)
arrow(ax, (72, 34.5), (77, 34.5), C_VLA)
arrow(ax, (22, 10.5), (27, 10.5), C_ACT)
arrow(ax, (47, 10.5), (52, 10.5), C_ACT)
arrow(ax, (72, 10.5), (77, 10.5), C_ACT)
arrow(ax, (91, 10.5), (99, 17.5), C_ACT)          # action -> robot
arrow(ax, (84, 30), (105, 27.5), C_VLA)           # z_rl -> robot (VLA 段)
arrow(ax, (105, 18), (105, 14), C_CRIT)           # robot -> reward
arrow(ax, (97, 9.5), (72, 20), C_CRIT)            # reward -> buffer
arrow(ax, (62, 25.5), (62, 42.2), C_CRIT)         # buffer -> critic
arrow(ax, (52, 42.5), (55, 15.5), C_CRIT, ls="--")  # critic -> actor
arrow(ax, (32, 15), (45, 29.5), "#6C8EBF", ls="--") # demos -> embeddings
arrow(ax, (84, 30), (62, 15.5), C_VLA, ls="--")     # z_rl -> actor

ax.text(62.5, 51.5, "冻结 VLA 主干不动：RL 只学关键阶段的小策略（Actor），状态用 VLA 内部表征压缩成 z_rl",
        ha="center", fontsize=10.5, color="#333333")
fig.savefig(IMG / "20_rl_pipeline.png", dpi=180, bbox_inches="tight")
plt.close(fig)

# ---------------- fig 2: critical phase timeline ----------------
rng = np.random.default_rng(7)
t = np.linspace(0, 10, 400)

fig, axes = plt.subplots(2, 1, figsize=(11.5, 5.6), sharex=True,
                         gridspec_kw={"height_ratios": [1, 2], "hspace": 0.14})

ax = axes[0]
ax.axvspan(0, 4.0, color=C_VLA, alpha=0.25)
ax.axvspan(4.0, 7.0, color=C_ACT, alpha=0.45)
ax.axvspan(7.0, 10, color=C_VLA, alpha=0.25)
ax.text(2.0, 0.55, "接近段\n冻结 VLA", ha="center", fontsize=10, color="#2F4B7C")
ax.text(5.5, 0.55, "关键阶段：对准→插入\nActor 接管", ha="center", fontsize=10.5,
        color="#8C4A1F", weight="bold")
ax.text(8.5, 0.55, "到位/收尾\n冻结 VLA", ha="center", fontsize=10, color="#2F4B7C")
ax.axvline(4.0, color=C_ACT, lw=1.5, ls="--"); ax.axvline(7.0, color=C_VLA, lw=1.5, ls="--")
ax.set_ylim(0, 1); ax.set_yticks([])
ax.set_ylabel("回合", fontsize=10)
for x, lab in [(4.0, "关键阶段开\n(c / 分类器)"), (7.0, "关键阶段关")]:
    ax.annotate(lab, xy=(x, 0.9), xytext=(x, 1.45), fontsize=8.5, ha="center",
                color="#555555", annotation_clip=False)
ax.annotate("回合结束 → y/n 记奖励", xy=(10, 0.9), xytext=(9.9, 1.45),
            fontsize=8.5, ha="right", color=C_CRIT, annotation_clip=False)

ax = axes[1]
p = np.where(t < 4.0, 0.30 + 0.10 * np.sin(t * 2.1), np.where(
    t < 7.0, 0.90 - 0.04 * np.sin(t * 3.3), 0.35 - 0.06 * np.sin(t * 2.4)))
p += rng.normal(0, 0.035, t.shape)
p = np.clip(p, 0, 1)
ax.plot(t, p, color=C_CRIT, lw=1.8, label="关键阶段概率（分类器输出）")
ax.axhline(0.75, color="#B03A2E", ls=":", lw=1.4); ax.text(9.9, 0.77, "on 阈值 0.75", fontsize=8.5, color="#B03A2E", ha="right")
ax.axhline(0.45, color="#7D6608", ls=":", lw=1.4); ax.text(9.9, 0.40, "off 阈值 0.45", fontsize=8.5, color="#7D6608", ha="right")
ax.axvspan(4.0, 7.0, color=C_ACT, alpha=0.12)
ax.axvline(4.0, color=C_ACT, lw=1.2, ls="--"); ax.axvline(7.0, color=C_VLA, lw=1.2, ls="--")
ax.set_xlabel("回合内时间 (s)"); ax.set_ylabel("概率", fontsize=10)
ax.set_ylim(0, 1.05); ax.set_xlim(0, 10)
ax.legend(loc="lower left", fontsize=9, frameon=False)

fig.savefig(IMG / "21_rl_critical_phase.png", dpi=180, bbox_inches="tight")
plt.close(fig)

# ---------------- fig 3: training curves (schematic) ----------------
ep = np.arange(0, 41)

def smooth_logistic(x, x0, k, lo, hi):
    return lo + (hi - lo) / (1 + np.exp(-k * (x - x0)))

succ = smooth_logistic(ep, 24, 0.28, 0.32, 0.80) + rng.normal(0, 0.025, ep.shape)
succ[ep < 15] = 0.30 + rng.normal(0, 0.02, (ep < 15).sum())   # warmup 段 VLA only
succ = np.clip(succ, 0, 1)

take = np.where(ep < 15, 0, np.clip(smooth_logistic(ep, 26, 0.4, 0.05, 0.92)
                                    + rng.normal(0, 0.03, ep.shape), 0, 1))
q = smooth_logistic(ep, 18, 0.5, 0.15, 0.95) + rng.normal(0, 0.03, ep.shape)
q = np.clip(q, 0, 1)
closs = 0.9 * np.exp(-ep / 9) + 0.12 + rng.normal(0, 0.015, ep.shape)
closs = np.clip(closs, 0, 1)

fig, axes = plt.subplots(1, 3, figsize=(12.5, 3.6))
for ax in axes:
    ax.axvspan(0, 15, color=C_GRAY, alpha=0.10)
    ax.set_xlabel("回合数")

axes[0].plot(ep, succ, color=C_VLA, lw=2)
axes[0].set_ylim(0, 1); axes[0].set_title("任务成功率（滑动窗口）", fontsize=11)
axes[0].text(7.5, 0.08, "warmup：VLA only", ha="center", fontsize=8.5, color="#666666")
axes[0].axvline(15, color=C_GRAY, ls=":", lw=1.2)

axes[1].plot(ep, take, color=C_ACT, lw=2, label="Actor 接管帧占比")
axes[1].plot(ep, q, color=C_CRIT, lw=1.6, ls="--", label="Q 值（归一化）")
axes[1].set_ylim(0, 1); axes[1].set_title("关键阶段行为", fontsize=11)
axes[1].legend(fontsize=8.5, frameon=False, loc="center right")
axes[1].axvline(15, color=C_GRAY, ls=":", lw=1.2)

axes[2].plot(ep, closs, color=C_CRIT, lw=2)
axes[2].set_ylim(0, 1); axes[2].set_title("Critic loss", fontsize=11)
axes[2].axvline(15, color=C_GRAY, ls=":", lw=1.2)

fig.suptitle("Stage 2 在线训练指标（示意曲线，实机训练后替换为 rl_metrics.log 实测图）",
             fontsize=10.5, color="#555555", y=1.02)
fig.savefig(IMG / "22_rl_training_curves.png", dpi=180, bbox_inches="tight")
plt.close(fig)

print("saved:", [p.name for p in sorted(IMG.glob("2*_rl_*.png"))])
