# 全流程命令清单

本文档汇总项目中使用过的全部命令。详见 `SO101机械臂微调π0.5学习记录.docx` 对应章节。

## 环境变量（~/.bashrc）

```bash
export LEADER=/dev/serial/by-id/usb-1a86_USB_Single_Serial_5B8E112957-if00
export FOLLOWER=/dev/serial/by-id/usb-1a86_USB_Single_Serial_5B8E116614-if00
export FRONT_CAM=/dev/v4l/by-id/<桌前相机固定路径>
export WRIST_CAM=/dev/v4l/by-id/<腕部相机固定路径>
export HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1
```

## 1. 安装

```bash
conda create -y -n lerobot python=3.12
conda activate lerobot
conda install -y -c conda-forge ffmpeg
pip install -i https://pypi.org/simple "lerobot[core_scripts,training,pi,feetech]"

# π0.5 权重（ModelScope，断点续传）
curl -fL -C - --retry 20 --retry-delay 5 --retry-all-errors \
  -o ~/models/pi05_base/model.safetensors \
  "https://modelscope.cn/models/lerobot/pi05_base/resolve/master/model.safetensors"
```

## 2. 标定与遥操作测试

```bash
lerobot-calibrate --robot.type=so101_follower --robot.port=$FOLLOWER --robot.id=my_follower
lerobot-calibrate --teleop.type=so101_leader --teleop.port=$LEADER --teleop.id=my_leader

lerobot-teleoperate \
  --robot.type=so101_follower --robot.port=$FOLLOWER --robot.id=my_follower \
  --teleop.type=so101_leader --teleop.port=$LEADER --teleop.id=my_leader
```

## 3. 数据采集

```bash
# 方向键关闭自动重复，防止误触连发（录完恢复：xset r on）
xset r off

lerobot-record \
  --robot.type=so101_follower --robot.port=$FOLLOWER --robot.id=my_follower \
  --robot.cameras="{ front: {type: opencv, index_or_path: $FRONT_CAM, width: 640, height: 480, fps: 30},
                     wrist: {type: opencv, index_or_path: $WRIST_CAM, width: 640, height: 480, fps: 30}}" \
  --teleop.type=so101_leader --teleop.port=$LEADER --teleop.id=my_leader \
  --dataset.repo_id=local/so101_clip_cup \
  --dataset.root=$HOME/.cache/huggingface/lerobot/local/so101_clip_cup \
  --dataset.no_stamp=true \
  --dataset.single_task="Put the clip into the cup" \
  --dataset.num_episodes=6 \
  --dataset.episode_time_s=50 --dataset.reset_time_s=15 \
  --dataset.streaming_encoding=true --dataset.encoder_threads=2 \
  --dataset.push_to_hub=false \
  --resume=true        # 第一次录制去掉这一行
```

键盘：→ 提前结束当前条；← 丢弃当前条重录；Esc 结束录制。

## 4. 数据清洗与检查

```bash
# 删除指定 episode（先备份！）
lerobot-edit-dataset \
  --repo_id=local/so101_clip_cup --root=<原目录> \
  --operation.type=delete_episodes --operation.episode_indices="[i, j]" \
  --new_repo_id=local/so101_clip_cup_clean --new_root=<新目录>

# 逐条回放检查
lerobot-dataset-viz --repo-id local/so101_clip_cup \
  --root=$HOME/.cache/huggingface/lerobot/local/so101_clip_cup

# 生成 episode 首尾帧拼图（code/preview.py）
python code/preview.py
```

## 5. 训练（π0.5，只训练动作专家）

```bash
export HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1

lerobot-train \
  --policy.path=/home/pc/models/pi05_base \
  --policy.device=cuda --policy.dtype=bfloat16 \
  --policy.train_expert_only=true \
  --policy.gradient_checkpointing=true \
  --policy.push_to_hub=false \
  --dataset.repo_id=local/so101_clip_cup \
  --dataset.root=$HOME/.cache/huggingface/lerobot/local/so101_clip_cup \
  --rename_map='{"observation.images.front": "observation.images.base_0_rgb",
                 "observation.images.wrist": "observation.images.left_wrist_0_rgb"}' \
  --batch_size=16 --num_workers=4 \
  --steps=6000 --save_freq=2000 --log_freq=100 \
  --wandb.enable=false \
  --output_dir=$HOME/outputs/train/pi05_so101_clip_cup
```

## 6. 部署评估（episodic rollout）

```bash
lerobot-rollout \
  --strategy.type=episodic \
  --policy.path=$HOME/outputs/train/pi05_so101_clip_cup/checkpoints/last/pretrained_model \
  --policy.device=cuda \
  --rename_map='{"observation.images.front": "observation.images.base_0_rgb",
                 "observation.images.wrist": "observation.images.left_wrist_0_rgb"}' \
  --robot.type=so101_follower --robot.port=$FOLLOWER --robot.id=my_follower \
  --robot.cameras="{ front: {type: opencv, index_or_path: $FRONT_CAM, width: 640, height: 480, fps: 30},
                     wrist: {type: opencv, index_or_path: $WRIST_CAM, width: 640, height: 480, fps: 30}}" \
  --dataset.repo_id=local/rollout_so101_clip_cup \
  --dataset.single_task="Put the clip into the cup" \
  --dataset.num_episodes=10 \
  --dataset.episode_time_s=30 --dataset.reset_time_s=15 \
  --dataset.push_to_hub=false
```

可选推理参数：

```bash
  --policy.n_action_steps=15        # 更频繁重规划（有停顿问题，见文档 10.1）
  --inference.type=rtc \
  --inference.rtc.execution_horizon=10 \
  --inference.rtc.max_guidance_weight=10.0   # RTC 推理
```

## 7. DAgger 纠正采集

```bash
python ~/lerobot_tools/dagger_with_home.py \
  --policy.path=$HOME/outputs/train/pi05_so101_clip_cup/checkpoints/last/pretrained_model \
  --robot.port=$FOLLOWER --front_cam=$FRONT_CAM --wrist_cam=$WRIST_CAM \
  --dataset.repo_id=local/rollout_so101_dagger ...
```

键位：空格 暂停/恢复策略；Tab 接管/交还；→ 回 home 位（自加）；Esc 结束。
只录制接管期间的画面与动作。

## 8. 数据集合并

```bash
# 原示范 + 审核后的 DAgger 纠正（code/merge_dagger.py，内嵌跳过清单）
python code/merge_dagger.py
# 输出：local/so101_clip_cup_dagger2（73 episodes, 26780 frames）
```

## 9. 文档生成

```bash
# code/make_docx.py 生成 Word 学习记录
python code/make_docx.py
# code/make_figures.py、make_figures2.py 生成文档配图
```
