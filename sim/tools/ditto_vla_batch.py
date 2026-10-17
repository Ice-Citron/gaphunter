"""Run a native VLA (MolmoAct2 / pi05) on Ditto task 1 easy through GAPHUNTER_SIM=ditto.

  .venv/bin/python -m sim.tools.ditto_vla_batch molmoact2 --local 2 --deploy 5 --stop 14:30
Writes results/ditto_<policy>_{local,deploy}.csv (B's 12 columns), one row appended per finished trial.
Trials run one at a time: each starts its own model server on the GPU.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DITTO_LOCAL = {"dx": (-0.05, 0.05), "dy": (-0.02, 0.05), "yaw": (-15.0, 15.0)}    # reach-limited (sim/README.md)
DITTO_DEPLOY = {"dx": (-0.12, 0.12), "dy": (-0.02, 0.20), "yaw": (-90.0, 90.0)}
CONFIGS = {"molmoact2": "molmoact2_ditto.json", "pi05": "pi05_ditto.json"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("policy", choices=sorted(CONFIGS))
    ap.add_argument("--local", type=int, default=2)
    ap.add_argument("--deploy", type=int, default=5)
    ap.add_argument("--stop", default="14:30", help="local wall-clock HH:MM; no trial starts after it")
    args = ap.parse_args()
    os.environ["GAPHUNTER_SIM"] = "ditto"
    os.environ["GAPHUNTER_DITTO_CONFIG"] = CONFIGS[args.policy]
    os.environ.setdefault("GAPHUNTER_FRICTION", "native")  # benchmark's own task, same as the astra-live seeds 13-14
    os.environ.setdefault("GAPHUNTER_TRIAL_TIMEOUT_S", "900")
    from runner.sample import sample_box
    from sim.trial import run_trial

    cols = list(pd.read_csv(ROOT / "results" / "local.csv", nrows=0).columns)
    stop = dt.datetime.combine(dt.date.today(), dt.time.fromisoformat(args.stop))
    plan = [("local", p) for p in sample_box(DITTO_LOCAL, args.local, seed=100)] + \
           [("deploy", p) for p in sample_box(DITTO_DEPLOY, args.deploy, seed=200)]
    for box, params in plan:
        if dt.datetime.now() >= stop:
            print(f"stop time {args.stop} reached; not starting more trials", flush=True)
            break
        r = run_trial(params, render=True)
        row = {"dx": params["dx"], "dy": params["dy"], "yaw": params["yaw"], "seed": params["seed"],
               "success": r.success, "failure_mode": r.failure_mode, "n_decisions": r.n_decisions,
               "t_wall": r.t_wall, "clip": r.clip, "transcript": r.transcript, "pose_error_mm": None, "pass": 1}
        out = ROOT / "results" / f"ditto_{args.policy}_{box}.csv"
        pd.DataFrame([row])[cols].to_csv(out, mode="a", header=not out.exists(), index=False)
        print(box, row, flush=True)


if __name__ == "__main__":
    main()
