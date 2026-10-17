"""run_trial for the MuJoCo peg-in-hole fallback: replay the cached Astra policy on one hole pose."""
from __future__ import annotations

import importlib.util
import json
import os
import signal
import time
from pathlib import Path

import numpy as np

from sim import api
from sim.ditto_trial import param_hash
from sim.mj_sim import ApiCapReached, CollisionStop, PegSim

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
POLICY_VERSION = os.environ.get("GAPHUNTER_POLICY", "v1")
WALL_LIMIT_S = int(os.environ.get("GAPHUNTER_TRIAL_TIMEOUT_S", "60"))
CLIP_FPS, CLIP_MAX_SECONDS = 15, 10.0
MIN_CLIP_BYTES = 50_000


class _WallTimeout(Exception):
    pass


def _load_policy():
    path = RESULTS / "policies" / f"{POLICY_VERSION}.py"
    spec = importlib.util.spec_from_file_location(f"gaphunter_policy_{POLICY_VERSION}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _exchange():
    path = RESULTS / "policies" / f"{POLICY_VERSION}.exchange.json"
    return json.loads(path.read_text()) if path.exists() else None


def _write_clip(frames, h):
    import imageio.v2 as imageio

    if not frames:
        return None
    max_frames = int(CLIP_FPS * CLIP_MAX_SECONDS)
    if len(frames) > max_frames:
        frames = [frames[i] for i in np.linspace(0, len(frames) - 1, max_frames).astype(int)]
    path = RESULTS / "clips" / f"{h}.mp4"
    path.parent.mkdir(parents=True, exist_ok=True)
    imageio.mimwrite(str(path), frames, fps=CLIP_FPS, macro_block_size=1)
    return str(path.relative_to(ROOT))


def run_mj_trial(params: dict, render: bool = False):
    from sim.trial import TrialResult

    t0 = time.time()
    h = param_hash(params)
    sim = PegSim(params, record_every=20 if render else 0)
    api._SIM = sim
    mode, error = "", None

    def _alarm(*_):
        raise _WallTimeout()

    previous = signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(WALL_LIMIT_S)
    try:
        _load_policy().run(api)
    except ApiCapReached:
        mode = "timeout"
    except _WallTimeout:
        mode, error = "timeout", f"wall clock > {WALL_LIMIT_S} s"
    except CollisionStop:
        mode = "collision"
    except Exception as exc:  # the policy itself crashed
        mode, error = "api_error", f"{type(exc).__name__}: {exc}"
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
        api._SIM = None
    outcome = sim.outcome()
    if outcome["success"] and mode != "collision":
        mode = ""
    elif not mode:
        mode = "miss"
    clip = None
    if render:
        sim._capture()
        try:
            clip = _write_clip(sim.frames, h)
            if clip and (ROOT / clip).stat().st_size < MIN_CLIP_BYTES:
                (ROOT / clip).unlink(missing_ok=True)
                clip = None  # too small to be a usable video
        except Exception:  # noqa: BLE001 - never fail a trial on rendering
            clip = None
        sim.close_renderer()
    outcome.update(failure_mode=mode, error=error, api_calls=sim.calls, pose_error_mm=sim.pose_error_mm)
    transcript = RESULTS / "transcripts" / f"{h}.json"
    transcript.parent.mkdir(parents=True, exist_ok=True)
    transcript.write_text(json.dumps({"params": {k: params[k] for k in ("dx", "dy", "yaw", "seed")},
                                      "policy_exchange": _exchange(), "steps": sim.log,
                                      "outcome": outcome}, indent=1, default=float))
    return TrialResult(dict(params), bool(outcome["success"] and mode == ""), mode, sim.calls,
                       time.time() - t0, clip,
                       str(transcript.relative_to(ROOT)), sim.pose_error_mm)
