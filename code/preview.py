import sys

import cv2
import numpy as np

from lerobot.datasets.lerobot_dataset import LeRobotDataset

HF = "/home/pc/.cache/huggingface/lerobot/local/"
out_prefix = sys.argv[1]
key = sys.argv[2]
names = sys.argv[3:]
rows = []
for name in names:
    ds = LeRobotDataset("local/" + name, root=HF + name)
    tag = name.split("_")[-1]
    for ep in range(ds.meta.total_episodes):
        a = ds.meta.episodes[ep]["dataset_from_index"]
        b = ds.meta.episodes[ep]["dataset_to_index"]
        tiles = []
        for t in np.linspace(a, b - 1, 8).astype(int):
            im = (ds[int(t)][key].permute(1, 2, 0).numpy() * 255).astype(np.uint8)[:, :, ::-1].copy()
            im = cv2.resize(im, (200, 150))
            cv2.putText(im, f"{tag} ep{ep} {(t - a) / 30:.0f}s", (4, 16), 0, 0.45, (0, 0, 255), 2)
            tiles.append(im)
        rows.append(np.hstack(tiles))
for i in range(0, len(rows), 4):
    cv2.imwrite(f"{out_prefix}_{i // 4}.jpg", np.vstack(rows[i:i + 4]))
print("rows", len(rows))
