"""Stub: re-exports the fake sim so A2/A3 can import sim.trial. Replaced in Phase 1."""
from __future__ import annotations

from dataclasses import dataclass

try:
    from runner.fake import TrialResult, fake_run_trial as run_trial  # noqa: F401
except ImportError:  # runner/fake.py not committed yet
    import random
    import time

    @dataclass
    class TrialResult:
        params: dict
        success: bool
        failure_mode: str
        n_decisions: int
        t_wall: float
        clip: str | None = None
        transcript: str | None = None

    def run_trial(params: dict, render: bool = False) -> TrialResult:
        t0 = time.time()
        rng = random.Random(hash((params.get("dx"), params.get("dy"), params.get("yaw"), params.get("seed"))))
        ok = abs(params["dx"]) < 0.08 and abs(params["dy"]) < 0.08 and abs(params["yaw"]) < 30
        if rng.random() < 0.05:
            ok = not ok
        return TrialResult(dict(params), ok, "" if ok else "miss", rng.randint(3, 15), time.time() - t0)

__all__ = ["TrialResult", "run_trial"]
