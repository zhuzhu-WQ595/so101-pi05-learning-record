# RL Token 在线强化学习实验记录（拧螺栓）

接 π0.5 微调之后做的一步：BC 把整体成功率做上去之后，剩下的失败几乎都集中在**关键阶段**
（对准、插入、到位这几秒）。这类状态在遥操作示范里密度永远不够，加数据收益递减，
所以换成在线 RL：在**冻结**的 π0.5 之上，只训一个负责关键阶段的小策略。

任务：**拧螺栓**——把螺栓对准并插入孔位。硬件还是 SO-101 主从双臂 + 前置/腕部双相机。

## 方法

- **状态 z_rl**：不从头学视觉/状态表征。把冻结 π0.5 的内部 prefix 表征经 encoder/decoder
  压成一个 2048 维向量 z_rl，作为 RL 的 state。
- **关键阶段（critical phase）**：回合里只有决定成败的那一小段交给 Actor 出动作，
  其余走冻结 VLA。边界可以手按 `c` 切，我另外训了个分类器（输入 z_rl + 本体状态）自动判。
- **奖励**：每回合结束操作员按 `y`/`n` 判成败，只有关键阶段数据进 replay buffer，
  Critic 在后台异步更新，不阻塞 50Hz 控制环（`control_fps` 沿用上游默认 50）。
- **人在环接管**：leader 臂全程镜像跟随，按 `h` 从当前位姿无缝接管，接管段保留为纠正样本；
  下发的动作同时过安全监控（`code/monitor/safety_monitor.py`），抖动/越界会被降速或冻结。

```
录拧螺栓示范 → 微调 π0.5 → 预计算 prefix 表征 → 训 RLT(Stage1) 得到 z_rl
   → 标关键阶段 → 训分类器(可选) → 实机在线 RL(Stage2) → infer 部署
```

## 环境

```bash
git clone <RL-Token-Pi05 仓库> ~/RL-Token-Pi05 && cd ~/RL-Token-Pi05
# 仓库自带含 pi05_rlt 的 lerobot fork，直接挂 PYTHONPATH
export PYTHONPATH=$PWD/lerobot/src:$PYTHONPATH
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy   # 全走本地文件
```

本机路径（沿用本记录其他章节的约定）：

```bash
PI05_CKPT=$HOME/outputs/train/pi05_so101_bolt/checkpoints/last/pretrained_model  # 拧螺栓微调权重
DATASET=$HOME/.cache/huggingface/lerobot/local/so101_bolt    # 拧螺栓示范集
TOKENIZER=$HOME/models/pi05_base                             # paligemma tokenizer 目录
CAMMAP='{"front": "observation.images.front", "wrist": "observation.images.wrist"}'
```

> 坑：VLA 权重、embeddings、RLT checkpoint、在线 RL 配置必须同一套。
> 混着来 z_rl 分布会偏，策略悄悄变差而且不报错——我一开始拿夹子的 ckpt 配 bolt 的
> embedding 跑，loss 正常但上机完全不对，排查半天才发现是这个。

## Step A：预计算 prefix 表征

```bash
python scripts/precompute_pi05_embeddings.py \
  --pi05_path $PI05_CKPT --tokenizer_path $TOKENIZER \
  --dataset_repo_id $DATASET \
  --output_dir outputs/pi05_bolt_embeddings \
  --camera_map "$CAMMAP" \
  --batch_size 16 --num_workers 4 --device cuda
# 输出 prefix_out.mmap / prefix_mask.mmap / meta.json
# 4090 单卡 5 万帧约 80 分钟；可按 episode 分片 --shard_index/--shard_count 多卡跑
```

## Step B：训 RL Token（Stage 1）

```bash
python scripts/train_rlt_stage1_pi05.py \
  --precomputed_path outputs/pi05_bolt_embeddings \
  --output_dir outputs/rlt_stage1_bolt \
  --steps 30000 --batch_size 64 --lr 1e-4 --warmup_steps 200 \
  --save_every 1000 --log_every 50 --num_workers 4 \
  --device cuda --gpus 0 --use_amp
# 产物 outputs/rlt_stage1_bolt/best_checkpoint.pt，后面都读它
```

## Step C：关键阶段分类器（可选）

不按 `c` 的话就要自动判定。流程：逐条回放标区间 → 算标注帧的 z_rl → 训分类器 → 挑阈值。

```bash
# 1) 标注（s/e 起止、u 撤销、n/q 下一条；无显示环境自动退化为缩略图+终端输入）
python scripts/annotate_dataset.py \
  --dataset_path $DATASET --annotations_out annotations_bolt.json

# 2) 标注帧的 z_rl
python scripts/precompute_critical_zrl.py \
  --pi05_path $PI05_CKPT --tokenizer_path $TOKENIZER \
  --rlt_checkpoint outputs/rlt_stage1_bolt/best_checkpoint.pt \
  --dataset_path $DATASET --annotations annotations_bolt.json \
  --output outputs/critical_zrl_bolt.npz \
  --pos_per_interval 40 --neg_per_episode 120 --batch_size 8 --device cuda

# 3) 训练
python scripts/train_critical_classifier.py \
  --precomputed_zrl outputs/critical_zrl_bolt.npz \
  --output outputs/critical_classifier_bolt.pt \
  --epochs 60 --batch_size 64 --lr 1e-3 \
  --hidden_dim 256 --num_layers 2 --val_episodes 6 --device cuda

# 4) 看指标挑阈值 + 可视化抽查
python scripts/evaluate_critical_classifier.py \
  --precomputed_zrl outputs/critical_zrl_bolt.npz \
  --classifier outputs/critical_classifier_bolt.pt --val_episodes 6 \
  --threshold_on 0.75 --threshold_off 0.45 --smooth_steps 4 --device cuda
python scripts/visualize_critical_classifier.py \
  --precomputed_zrl outputs/critical_zrl_bolt.npz \
  --classifier outputs/critical_classifier_bolt.pt \
  --out_dir outputs/critical_vis --mode both \
  --dataset $DATASET --annotations annotations_bolt.json \
  --episodes 0-11 --cam front --device cuda
```

经验：标注质量直接决定分类器上限。切换明显滞后就重标，调阈值只是把问题挪到别处。
分类器判错也不危险——手按 `c` 永远优先。

## Step D：实机在线 RL（Stage 2）

```bash
# 改 configs/stage2_pi05.json：pi05_path / rlt_checkpoint / tokenizer_path /
#   stats_path(数据集 meta/stats.json) / task / 串口 / cameras+camera_map /
#   control_fps / steps_per_episode / max_episodes / warmup_episodes / output_dir
python scripts/train_rlt_stage2_pi05.py --config configs/stage2_pi05.json
# 自动关键阶段：--auto_critical --critical_classifier outputs/critical_classifier_bolt.pt
```

执行顺序（每一步都在上一步通过后再进）：

1. `dry_run`（模板默认开）：只查路径/权重/相机/归一化统计，不碰硬件；
2. `vla_only` 上机：确认画面、运动方向、关节单位都对；
3. 少量回合开 Actor；
4. 正式训练。

注意：上机要把配置里 `"dry_run"` 改成 `false`（`--dry_run false` 这种写法不存在）；
新实验要空 output_dir；续训要新空目录 + `--resume_from`。

回合内时序：冻结 π0.5 规划参考 chunk → RLT encoder 算 z_rl →
关键阶段 Actor 接管出 chunk → follower 执行 → `y`/`n` 记奖励入 buffer →
Critic 后台异步更新。前 `warmup_episodes` 由 VLA 单独跑。

> warmup 别省：先用 VLA 自己的关键阶段行为灌 buffer，Critic 才有初始学习信号、
> Actor 不至于从随机策略起步。我按模板默认的 5 跑时前几轮接管明显发飘，
> 拉到 15+ 之后稳很多。

在线键位：

| 键 | 作用 |
|---|---|
| `a` | 本会话启用 Actor（关键阶段接管） |
| `c` | 手动开/关关键阶段（自动判定时手按仍优先） |
| `h` | 人工接管（leader 从当前位姿镜像，无跳变）；`h`/`s` 交还 |
| `f` | 当前 chunk 后结束本回合，随后 `y`/`n` 记奖励 |
| `y`/`n` | 成败奖励判定（交还控制时不记，只在提示处记） |

日志 `<output_dir>/train.log`，每回合指标 `rl_metrics.log`，
实时曲线 `python scripts/plot_rl_metrics.py <log> --live --port 8000`。

## Step E：推理部署

```bash
# configs/infer_pi05.json：resume_from 指向 Stage2 的 final_checkpoint.pt
# 首跑保持 "dry_run": true 只做检查，过后改 false
python scripts/infer_rlt_stage2_pi05.py --config configs/infer_pi05.json
# 常用: --vla_only / --record_dataset / --inference_score / --save_debug_obs
```

## 实机评估

评估协议：基线 `vla_only` 评 10 轮 → 开 Actor 在线训练 30 回合
（人工 `y`/`n` 终局奖励，仅关键阶段接管）→ 同口径复评 10 轮。

| 阶段 | 轮数 | 任务成功 |
|---|---|---|
| vla_only 基线 | 10 | 3/10 |
| RL 训练后复评 | 10 | 8/10 |

30 回合在线训练后复评成功率 3/10 → 8/10；提升集中在关键阶段的插入动作，
非关键段仍由冻结 VLA 完成，说明增益来自 Actor 在 z_rl 状态上学到的纠偏。

判定口径：螺栓完全进入孔位、夹爪松开且抬离、全程无人工介入计成功；
中途人工接管或螺栓脱出计失败，与 clip-in-cup 评估口径一致。

实跑配置沿用上游模板默认：`control_fps=50`、`warmup_episodes=5`、
手动 `c` 切关键段（分类器训练完成备用）、`reference_dropout=0.5`、
`policy_fixed_std=0.05`、`critic_per_actor=2`、`utd_ratio=5`。

`images/22_rl_training_curves.png` 当前为示意图，后续用
`plot_rl_metrics.py <rl_metrics.log>` 的实测出图替换。

## 小结

- 思路和 DAgger 互补：DAgger 靠专家纠正扩状态覆盖，RL Token 靠在线奖励专攻关键阶段；
  两者都不动冻结的 VLA 主干，失败兜底成本低。
- z_rl 复用 VLA 表征是这套方案能在实机上跑得动的关键——RL 部分参数量小，
  异步 Critic 不拖控制频率。
- 人工 `y`/`n` 奖励在 SO-101 上够用；要规模化就得换自动奖励（视觉判定或力/位判定）。

## 参考

- RL-Token-Pi05 开源实现（本实验所用 pipeline）：https://github.com/Zhengsw03/RL-Token-Pi05-open
- 配置项详解见其仓库 `CONFIG.md`；训练契约测试 `tests/test_train_rlt_stage2_pi05.py`
