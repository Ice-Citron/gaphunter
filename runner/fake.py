"""Fake sim: success iff |dx|<0.08 and |dy|<0.08 and |yaw|<30, with 5% seeded flips."""
from __future__ import annotations

import random
import sys
from dataclasses import dataclass

try:
    from sim.trial import TrialResult
except ImportError:  # sim.trial missing, or mid-import (sim.trial re-exports this module)
    print("WARNING runner.fake: sim.trial.TrialResult unavailable, using local copy", file=sys.stderr)

    @dataclass
    class TrialResult:
        params: dict
        success: bool
        failure_mode: str
        n_decisions: int
        t_wall: float
        clip: str | None = None
        transcript: str | None = None


def fake_run_trial(params: dict, render: bool = False) -> TrialResult:
    ok = abs(params["dx"]) < 0.08 and abs(params["dy"]) < 0.08 and abs(params["yaw"]) < 30
    rng = random.Random(params["seed"])
    ok = (not ok) if rng.random() < 0.05 else ok
    if ok:
        mode = ""
    elif abs(params["dx"]) >= 0.08 or abs(params["dy"]) >= 0.08:
        mode = "miss"
    else:
        mode = "timeout"
    return TrialResult(dict(params), ok, mode, n_decisions=rng.randint(4, 15), t_wall=0.01,
                       clip=None, transcript=None)
