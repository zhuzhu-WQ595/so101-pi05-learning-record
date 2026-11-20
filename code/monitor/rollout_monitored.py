#!/usr/bin/env python
"""lerobot-rollout 的带安全监控版启动器。

复刻官方 lerobot_rollout.main() 流程，仅把 robot_action_processor
换成含 SafetyMonitorStep 的版本。用法与官方命令完全一致，额外加：

    --demo_root   示范数据集路径（用于在线标定，默认 so101_block_stack_clean）
    --monitor.*   阈值参数（可选）

例：
    python rollout_monitored.py \
        --strategy.type=base \
        --policy.path=/home/pc/outputs/train/pi05_so101_block_stack/checkpoints/last/pretrained_model \
        --inference.type=rtc --inference.rtc.execution_horizon=10 \
        --robot.type=so101_follower --robot.port=/dev/ttyACM0 \
        --robot.cameras='{ front: {type: opencv, index_or_path: 0}, wrist: {type: opencv, index_or_path: 2}}' \
        --task="Put the red block on the blue block" --duration=60
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lerobot.configs import parser
from lerobot.scripts.lerobot_rollout import init_logging, ProcessSignalHandler
from lerobot.utils.import_utils import register_third_party_plugins
from lerobot.utils.visualization_utils import init_visualization, shutdown_visualization
from lerobot.rollout import RolloutConfig, build_rollout_context, create_strategy

from safety_monitor import MonitorConfig, calibrate_from_dataset, make_monitored_processors

logger = logging.getLogger("rollout_monitored")

DEFAULT_DEMO = "/home/pc/.cache/huggingface/lerobot/local/so101_block_stack_clean"


@parser.wrap()
def rollout(cfg: RolloutConfig):
    init_logging()
    demo_root = parser.parse_arg("demo_root", DEFAULT_DEMO)
    if isinstance(demo_root, list):
        demo_root = demo_root[0] if demo_root else DEFAULT_DEMO

    logger.info("Calibrating monitor from demo dataset: %s", demo_root)
    cal = calibrate_from_dataset(demo_root)
    logger.info(
        "Calibration done: speed=%.1f±%.1f accel=%.1f±%.1f track=%.1f±%.1f",
        cal["speed"][0], cal["speed"][1], cal["accel"][0], cal["accel"][1],
        cal["track_err"][0], cal["track_err"][1],
    )

    teleop_p, robot_action_p, robot_obs_p = make_monitored_processors(calibration=cal)

    signal_handler = ProcessSignalHandler(use_threads=True, display_pid=False)
    shutdown_event = signal_handler.shutdown_event

    logger.info("Building rollout context (with safety monitor)...")
    ctx = build_rollout_context(
        cfg, shutdown_event,
        teleop_action_processor=teleop_p,
        robot_action_processor=robot_action_p,
        robot_observation_processor=robot_obs_p,
    )
    strategy = create_strategy(cfg.strategy)
    logger.info("Strategy=%s | monitor: slow>%.1f (%d/%df) block>%.1f (%d/%df)",
                cfg.strategy.type,
                MonitorConfig().slow_thresh, MonitorConfig().slow_min_hits, MonitorConfig().slow_window,
                MonitorConfig().block_thresh, MonitorConfig().block_min_hits, MonitorConfig().block_window)

    if cfg.display_data:
        init_visualization(cfg.display_mode, session_name="rollout",
                           ip=cfg.display_ip, port=cfg.display_port)
    try:
        strategy.setup(ctx)
        logger.info("Rollout started (safety monitor ON)")
        strategy.run(ctx)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        strategy.teardown(ctx)
        if cfg.display_data:
            shutdown_visualization(cfg.display_mode)


def main():
    register_third_party_plugins()
    rollout()


if __name__ == "__main__":
    main()
