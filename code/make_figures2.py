import glob
from pathlib import Path

import cv2
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

from lerobot.datasets.lerobot_dataset import LeRobotDataset

OUT = Path("/home/pc/桌面/SO101_pi05_学习记录/images")
HF = "/home/pc/.cache/huggingface/lerobot/local/"
for f in font_manager.findSystemFonts():
    if "NotoSansCJK" in f:
        font_manager.fontManager.addfont(f)
plt.rcParams["font.family"] = "Noto Sans CJK SC"
plt.rcParams["axes.unicode_minus"] = False

BASE = "rollout_so101_clip_cup_20261025_200342"
NAS15 = "rollout_so101_nas15_20261026_193955"
RTC = "rollout_so101_rtc_20261026_194436"
TAPE_A = "rollout_so101_tape_20261026_195524"
TAPE_B = "rollout_so101_tape_20261026_200111"


def load_df(name):
    return pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(HF + name + "/data/**/*.parquet", recursive=True))])


def jumps(name):
    df = load_df(name)
    per_ep = []
    for _, g in df.groupby("episode_index"):
        a = np.stack(g["action"].values)[:, :5]
        per_ep.append(np.abs(np.diff(a, axis=0)).max(1))
    return per_ep


# ---- fig 11: action jump comparison ----
conf = [("原始同步推理\n(每 50 步推理一次)", BASE, "#4C72B0"),
        ("同步推理\nn_action_steps=15", NAS15, "#C44E52"),
        ("RTC 推理", RTC, "#55A868")]
fig, axes = plt.subplots(1, 2, figsize=(11, 3.8), dpi=150, gridspec_kw={"width_ratios": [2.2, 1]})
stats = []
for label, name, c in conf:
    d = jumps(name)
    seg = d[0][:600]
    axes[0].plot(np.arange(len(seg)) / 30, seg, color=c, lw=0.9, label=label.replace("\n", " "), alpha=0.85)
    allv = np.concatenate(d)
    stats.append((label, np.percentile(allv, 95), (allv > 3).sum() / (len(allv) / 30), c))
axes[0].set_xlabel("时间 (秒)")
axes[0].set_ylabel("相邻帧关节指令最大变化")
axes[0].set_title("每帧动作变化（每种条件第 1 轮，前 20 秒）")
axes[0].legend(fontsize=8)
axes[0].grid(alpha=0.3)
x = np.arange(len(stats))
axes[1].bar(x, [s[2] for s in stats], color=[s[3] for s in stats])
axes[1].set_xticks(x, [s[0] for s in stats], fontsize=8)
axes[1].set_ylabel("大跳变次数 / 秒（变化 > 3）")
axes[1].set_title("动作跳变频率")
for i, s in enumerate(stats):
    axes[1].text(i, s[2], f"{s[2]:.2f}", ha="center", va="bottom", fontsize=9)
fig.tight_layout()
fig.savefig(OUT / "11_inference_jumps.png")
plt.close(fig)
for s in stats:
    print("jumps", s[0].replace("\n", " "), "p95=%.2f" % s[1], "big/s=%.3f" % s[2])

# ---- fig 12: outcome comparison bar chart ----
cats = ["任务成功", "夹住但粘住", "打滑/抓不起", "碰跑", "人工介入"]
base = [7, 0, 2, 0, 1]
tape = [4, 4, 0, 3, 0]
base_pct = [v / 10 * 100 for v in base]
tape_pct = [v / 12 * 100 for v in tape]
fig, ax = plt.subplots(figsize=(8, 3.8), dpi=150)
x = np.arange(len(cats))
w = 0.38
b1 = ax.bar(x - w / 2, base_pct, w, label="原始（10 轮）", color="#4C72B0")
b2 = ax.bar(x + w / 2, tape_pct, w, label="夹子贴双面胶（12 轮）", color="#DD8452")
for bars, vals in ((b1, base), (b2, tape)):
    for r, v in zip(bars, vals):
        ax.text(r.get_x() + r.get_width() / 2, r.get_height() + 1, str(v), ha="center", fontsize=9)
ax.set_xticks(x, cats)
ax.set_ylabel("占比 (%)")
ax.set_title("两组实机评估的结果分布（柱上数字为轮数）")
ax.legend()
ax.grid(axis="y", alpha=0.3)
fig.tight_layout()
fig.savefig(OUT / "12_outcome_compare.png")
plt.close(fig)


# ---- screenshots ----
def frame(ds, idx, key):
    im = ds[int(idx)][key].permute(1, 2, 0).numpy()
    return (im * 255).astype(np.uint8)[:, :, ::-1].copy()


def label(im, text):
    cv2.rectangle(im, (0, 0), (len(text) * 13 + 14, 30), (0, 0, 0), -1)
    cv2.putText(im, text, (7, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
    return im


def seq_grid(name, ep, key, out, n=6, start=0.0, end=1.0):
    ds = LeRobotDataset("local/" + name, root=HF + name)
    a = ds.meta.episodes[ep]["dataset_from_index"]
    b = ds.meta.episodes[ep]["dataset_to_index"]
    lo, hi = a + int(start * (b - a)), a + int(end * (b - a)) - 1
    ts = [cv2.resize(label(frame(ds, t, key), f"t={(t - a) / 30:.1f}s"), (426, 320))
          for t in np.linspace(lo, hi, n).astype(int)]
    h = n // 2
    cv2.imwrite(str(OUT / out), np.vstack([np.hstack(ts[:h]), np.hstack(ts[h:])]))


def front_wrist_pair(name, ep, out, t_from_end_s=0.5):
    ds = LeRobotDataset("local/" + name, root=HF + name)
    b = ds.meta.episodes[ep]["dataset_to_index"]
    t = b - 1 - int(t_from_end_s * 30)
    pair = np.hstack([label(frame(ds, t, "observation.images.front"), "front"),
                      label(frame(ds, t, "observation.images.wrist"), "wrist")])
    cv2.imwrite(str(OUT / out), pair)


# baseline failure ep0: slip then pushed away (front + wrist)
seq_grid(BASE, 0, "observation.images.wrist", "13_base_fail_ep0_wrist.jpg")
# tape: success, stuck, knocked away
seq_grid(TAPE_B, 3, "observation.images.front", "14_tape_success_ep3_front.jpg")
front_wrist_pair(TAPE_B, 4, "15_tape_stuck_ep4.jpg")
seq_grid(TAPE_B, 2, "observation.images.front", "16_tape_knock_ep2_front.jpg")
seq_grid(TAPE_B, 7, "observation.images.wrist", "17_tape_knock_ep7_wrist.jpg", start=0.0, end=0.55)
print("done")
