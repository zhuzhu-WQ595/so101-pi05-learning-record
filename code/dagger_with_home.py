"""lerobot-rollout --strategy.type=dagger, plus a "→ = go home" key.

Usage: identical to `lerobot-rollout`, just replace the command with
    python ~/lerobot_tools/dagger_with_home.py <same arguments>

Extra key (only when NOT correcting):
    →      pause the policy, move the follower back to the pose it had at startup,
           and hold it there while you reset the scene.
    → / space (while holding at home)
           resume autonomous policy execution from the home pose.

The leader arm is treated as non-actuated (LEADER_ACTUATED = False): it is never
driven by its motors, which would brown out a weak 5 V leader power supply.
Instead, when a correction starts (Tab), the follower slides to the leader's pose.
"""

import logging
import threading
import time

from lerobot.rollout.strategies import dagger
from lerobot.rollout.strategies.core import RolloutStrategy
from lerobot.scripts import lerobot_rollout
from lerobot.utils.robot_utils import precise_sleep

logger = logging.getLogger("dagger_with_home")

HOME_REQUEST = threading.Event()
RESUME_REQUEST = threading.Event()
WAITING = threading.Event()
STATE = {"strategy": None, "ctx": None}

HOME_MOVE_S = 2.0
HOLD_FPS = 30
LEADER_ACTUATED = False

if not LEADER_ACTUATED:
    dagger.teleop_supports_feedback = lambda teleop: False

_orig_create_key_listener = dagger.create_key_listener


def _patched_create_key_listener(dispatch, *, controls_help=""):
    def wrapped(name):
        if name == "esc":
            RESUME_REQUEST.set()
            dispatch(name)
        elif WAITING.is_set():
            if name in ("right", "space"):
                RESUME_REQUEST.set()
        elif name == "right":
            HOME_REQUEST.set()
        else:
            dispatch(name)

    return _orig_create_key_listener(wrapped, controls_help=controls_help + ", RIGHT=go home / resume")


dagger.create_key_listener = _patched_create_key_listener

_orig_setup = dagger.DAggerStrategy.setup


def _patched_setup(self, ctx):
    STATE["strategy"], STATE["ctx"] = self, ctx
    _orig_setup(self, ctx)


dagger.DAggerStrategy.setup = _patched_setup

_orig_consume = dagger.DAggerEvents.consume_transition


def _go_home_and_wait(events):
    strategy, ctx = STATE["strategy"], STATE["ctx"]
    hw = ctx.hardware
    if not hw.initial_position:
        logger.warning("No initial position captured; ignoring go-home request")
        return False

    WAITING.set()
    strategy._engine.pause()
    logger.info("Go home: moving follower to startup pose")
    RolloutStrategy._return_to_initial_position(hw, duration_s=HOME_MOVE_S)

    RESUME_REQUEST.clear()
    logger.info("Holding at home. Reset the scene, then press → or space to resume the policy.")
    print("\n>>> 已归位。布置好环境后按 → 或 空格，模型继续运行（Esc 结束）\n", flush=True)
    try:
        while not (
            RESUME_REQUEST.is_set() or events.stop_recording.is_set() or ctx.runtime.shutdown_event.is_set()
        ):
            t0 = time.perf_counter()
            hw.robot_wrapper.send_action(dict(hw.initial_position))
            precise_sleep(max(0.0, 1 / HOLD_FPS - (time.perf_counter() - t0)))
    finally:
        WAITING.clear()
        RESUME_REQUEST.clear()
    return not events.stop_recording.is_set()


def _patched_consume(self):
    if HOME_REQUEST.is_set():
        HOME_REQUEST.clear()
        with self._lock:
            old_phase = self._phase
        if old_phase == dagger.DAggerPhase.CORRECTING:
            logger.info("Go-home ignored while correcting; press Tab to finish the correction first")
        elif _go_home_and_wait(self):
            with self._lock:
                self._phase = dagger.DAggerPhase.AUTONOMOUS
                self._pending_transition = None
            return old_phase, dagger.DAggerPhase.AUTONOMOUS
    return _orig_consume(self)


dagger.DAggerEvents.consume_transition = _patched_consume

if __name__ == "__main__":
    lerobot_rollout.main()
