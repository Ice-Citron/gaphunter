"""run_trial: one GapHunter episode. Fake backend until the Ditto wrapper lands (GAPHUNTER_SIM=ditto)."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class TrialResult:
    params: dict            # echoed
    success: bool
    failure_mode: str       # "" | "miss" | "drop" | "timeout" | "collision" | "api_error"
    n_decisions: int        # Astra calls made
    t_wall: float           # seconds
    clip: str | None = None        # results/clips/<hash>.mp4, if rendered
    transcript: str | None = None  # results/transcripts/<hash>.json


def run_trial(params: dict, render: bool = False) -> TrialResult:
    if os.environ.get("GAPHUNTER_SIM", "fake") == "ditto":
        from sim.ditto_trial import run_ditto_trial
        return run_ditto_trial(params, render=render)
    from runner.fake import fake_run_trial  # lazy: runner.fake imports TrialResult from here
    return fake_run_trial(params, render=render)


__all__ = ["TrialResult", "run_trial"]
