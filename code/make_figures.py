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
OUT.mkdir(parents=True, exist_ok=True)
HF = "/home/pc/.cache/huggingface/lerobot/"

for f in font_manager.findSystemFonts():
    if "NotoSansCJK" in f.replace(" ", "") or "NotoSansCJK-Regular" in f:
        font_manager.fontManager.addfont(f)
plt.rcParams["font.family"] = "Noto Sans CJK SC"
plt.rcParams["axes.unicode_minus"] = False


def frame(ds, idx, key):
    im = ds[int(idx)][key].permute(1, 2, 0).numpy()
    return (im * 255).astype(np.uint8)[:, :, ::-1].copy()


def label(im, text):
    cv2.rectangle(im, (0, 0), (len(text) * 13 + 14, 30), (0, 0, 0), -1)
    cv2.putText(im, text, (7, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
    return im


train = LeRobotDataset("local/so101_clip_cup", root=HF + "local/so101_clip_cup")
roll_repo = "local/rollout_so101_clip_cup_20261025_200342"
roll = LeRobotDataset(roll_repo, root=HF + roll_repo)

# 1. dual camera view from the training data
s = train.meta.episodes[1]["dataset_from_index"] + 150
pair = np.hstack([label(frame(train, s, "observation.images.front"), "front (main camera)"),
                  label(frame(train, s, "observation.images.wrist"), "wrist camera")])
cv2.imwrite(str(OUT / "01_dual_camera.jpg"), pair)

# 2. live front camera view
live = cv2.imread("/tmp/front_live.jpg")
if live is not None:
    cv2.imwrite(str(OUT / "02_front_live.jpg"), live)

# 3. training samples at grasp moment
picks = {4: 177, 35: 203, 10: 148, 1: 215, 22: 175, 0: 0}
tiles = []
for ep, fr in picks.items():
    im = frame(train, train.meta.episodes[ep]["dataset_from_index"] + fr, "observation.images.front")
    tiles.append(cv2.resize(label(im, f"episode {ep}"), (426, 320)))
cv2.imwrite(str(OUT / "03_train_samples.jpg"), np.vstack([np.hstack(tiles[:3]), np.hstack(tiles[3:])]))


def sequence(ds, ep, n, key, name, fracs=None):
    a = ds.meta.episodes[ep]["dataset_from_index"]
    b = ds.meta.episodes[ep]["dataset_to_index"]
    idxs = np.linspace(a, b - 1, n).astype(int) if fracs is None else [int(a + f * (b - 1 - a)) for f in fracs]
    ts = []
    for i, t in enumerate(idxs):
        im = frame(ds, t, key)
        ts.append(cv2.resize(label(im, f"t={(t - a) / 30:.1f}s"), (426, 320)))
    half = len(ts) // 2
    grid = np.vstack([np.hstack(ts[:half]), np.hstack(ts[half:])])
    cv2.imwrite(str(OUT / name), grid)


# 4. rollout successes (front) + one with wrist view
sequence(roll, 9, 6, "observation.images.front", "04_rollout_success_ep9_front.jpg")
sequence(roll, 9, 6, "observation.images.wrist", "05_rollout_success_ep9_wrist.jpg")
sequence(roll, 2, 6, "observation.images.front", "06_rollout_success_ep2_front.jpg")
# 5. rollout failure
sequence(roll, 0, 6, "observation.images.front", "07_rollout_fail_ep0_front.jpg")

# ---- charts from training data ----
df = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(HF + "local/so101_clip_cup/data/**/*.parquet", recursive=True))])
lens, grasp, grip = [], [], []
for ep, g in df.groupby("episode_index"):
    a = np.stack(g["action"].values)
    st = np.stack(g["observation.state"].values)
    lens.append(len(g) / 30)
    ga = a[:, 5]
    imax = int(np.argmax(ga[: len(ga) * 2 // 3]))
    thr = (ga[imax] + ga[imax:].min()) / 2
    c = imax + int(np.argmax(ga[imax:] < thr))
    grasp.append(st[c, :5])
    after = ga[c + 10:]
    reopen = int(np.argmax(after > thr)) if (after > thr).any() else len(after)
    w = slice(c + 10, c + 10 + max(reopen, 1))
    grip.append((ga[w].mean(), st[w, 5].mean()))
    if ep == 1:
        ex_a, ex_s = ga, st[:, 5]
grasp = np.array(grasp)
grip = np.array(grip)

fig, ax = plt.subplots(figsize=(6, 3.6), dpi=150)
ax.hist(lens, bins=12, color="#4C72B0", edgecolor="white")
ax.set_xlabel("单条示范时长 (秒)")
ax.set_ylabel("条数")
ax.set_title(f"50 条示范的时长分布（平均 {np.mean(lens):.1f} 秒）")
fig.tight_layout()
fig.savefig(OUT / "08_episode_length.png")
plt.close(fig)

fig, ax = plt.subplots(figsize=(6, 4), dpi=150)
ax.scatter(grasp[:, 0], grasp[:, 2], c="#DD8452", s=40, edgecolor="k", linewidth=0.5)
ax.set_xlim(-100, 100)
ax.set_xlabel("shoulder_pan（底座左右转角，归一化 -100~100）")
ax.set_ylabel("elbow_flex（肘关节，决定远近）")
ax.set_title("每条示范夹爪闭合时刻的关节位置：抓取区域高度集中")
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(OUT / "09_grasp_coverage.png")
plt.close(fig)

fig, ax = plt.subplots(figsize=(6.5, 3.6), dpi=150)
t = np.arange(len(ex_a)) / 30
ax.plot(t, ex_a, label="action（主臂指令）", color="#4C72B0")
ax.plot(t, ex_s, label="state（从臂实际）", color="#C44E52")
ax.set_xlabel("时间 (秒)")
ax.set_ylabel("夹爪开合（0=闭合，100=全开）")
ax.set_title("episode 1 夹爪曲线：夹住时指令与实际只差约 3")
ax.legend()
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(OUT / "10_gripper_curve.png")
plt.close(fig)

print("lens mean", np.mean(lens), "min", np.min(lens), "max", np.max(lens))
print("grip hold action mean", grip[:, 0].mean(), "state mean", grip[:, 1].mean())
print("done", sorted(p.name for p in OUT.iterdir()))
