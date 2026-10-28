"""Merge original demos + selected DAgger corrections into local/so101_clip_cup_dagger.

Skips:
  - rollout_so101_dagger_20261027_182644 entirely (single 1.6 s episode)
  - rollout_so101_dagger_20261027_182953 episodes 10, 11 (clip left on table)
  - rollout_so101_dagger_20261027_184441 (empty)
The extra 'intervention' column is dropped automatically (not in features).
"""

import json
import numpy as np
from torchcodec.decoders import VideoDecoder

from lerobot.datasets.lerobot_dataset import LeRobotDataset

HF = "/home/pc/.cache/huggingface/lerobot/local/"
TASK = "Put the clip into the cup"

SOURCES = [
    ("so101_clip_cup", None),                       # all 50 episodes
    ("rollout_so101_dagger_20261026_203527", None),
    ("rollout_so101_dagger_20261027_181709", {1, 3, 5}),  # jerky: frozen + spike segments
    ("rollout_so101_dagger_20261027_182953", {10, 11}),
]
CAM_KEYS = ["observation.images.front", "observation.images.wrist"]

OUT_REPO = "local/so101_clip_cup_dagger2"
OUT_ROOT = HF + "so101_clip_cup_dagger2"

orig = LeRobotDataset("local/so101_clip_cup", root=HF + "so101_clip_cup")
features = orig.features
print("features:", list(features))

out = LeRobotDataset.create(
    repo_id=OUT_REPO,
    fps=orig.fps,
    features=features,
    root=OUT_ROOT,
    robot_type=orig.meta.robot_type,
    use_videos=True,
)

total_eps = 0
total_frames = 0
for name, skip in SOURCES:
    ds = LeRobotDataset("local/" + name, root=HF + name)
    for ep in range(ds.meta.total_episodes):
        if skip and ep in skip:
            print(f"  skip {name}#{ep}")
            continue
        a = ds.meta.episodes[ep]["dataset_from_index"]
        b = ds.meta.episodes[ep]["dataset_to_index"]
        n = b - a
        rows = ds.hf_dataset.select(range(a, b)).to_pandas()
        vids = {}
        ep_meta = ds.meta.episodes[ep]
        for k in CAM_KEYS:
            path = ds.root / ds.meta.get_video_file_path(ep, k)
            dec = VideoDecoder(str(path))
            t0 = float(ep_meta[f"videos/{k}/from_timestamp"])
            t1 = float(ep_meta[f"videos/{k}/to_timestamp"])
            dur = getattr(dec.metadata, "duration_seconds", None) or len(dec) / ds.fps
            batch = dec.get_frames_played_in_range(max(t0 - 1e-3, 0.0), min(t1 + 1e-3, dur))
            pts = batch.pts_seconds
            keep = pts >= t0 - (0.5 / ds.fps)
            fr = batch.data[keep][:n]  # NCHW uint8; boundary can include next ep's first frame
            if fr.shape[0] != n:
                raise RuntimeError(f"{name} ep{ep} {k}: decoded {fr.shape[0]} frames, meta says {n}")
            vids[k] = fr.permute(0, 2, 3, 1).numpy()
        for i in range(n):
            frame = {
                "observation.state": np.asarray(rows["observation.state"].iloc[i], dtype=np.float32),
                "action": np.asarray(rows["action"].iloc[i], dtype=np.float32),
                "task": TASK,
            }
            for k in CAM_KEYS:
                frame[k] = vids[k][i]
            out.add_frame(frame)
        out.save_episode()
        total_eps += 1
        total_frames += n
        print(f"{name}#{ep}: {n} frames -> merged ep {total_eps - 1}")

out.finalize()
print(f"DONE: {total_eps} episodes, {total_frames} frames -> {OUT_ROOT}")
