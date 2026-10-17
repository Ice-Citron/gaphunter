"""Rebuild results/policies.json, the policy-comparison table, from whatever CSVs exist.

    python -m runner.policies

One object per policy row, in POLICIES order, with keys exactly:
    policy, family, model, task, sim, status, n_local, local_success, n_deploy, deploy_success,
    outside_success, local_csv, deploy_csv, notes
Rates follow analysis.coverage (pass == 1 rows, api_error rows dropped). A rate is null when its n is 0.
status: "full" = local and deploy trials, "smoke" = some trials, "planned" = no CSV yet.
CSV paths are relative to the repo root; a policy's CSV is results/<sim>_<policy>_<local|deploy>.csv
(policy with "-" or "_"), except astra-script, whose CSVs are results/local.csv and results/deploy.csv.
"""
from __future__ import annotations

import json
import sys

import pandas as pd

from analysis.coverage import _drop_infra, _success, first_pass, inside_local
from runner.batch import RESULTS, ROOT
from runner.sample import local_box

OUT = RESULTS / "policies.json"

DITTO_TASK = ("Ditto Bench task 1 (DittoOddGeometry-v1) easy: pick up the 48 mm sphere and put it in the basket, "
              "Franka FR3 + Robotiq 2F-85")
# Reach-limited Ditto local box (Agent A); "outside the local box" for Ditto rows is measured against it.
DITTO_LOCAL_BOX = {"dx": (-0.05, 0.05), "dy": (-0.02, 0.05), "yaw": (-15.0, 15.0)}

# "local_box" is used for outside_success only and is not written to the JSON.
POLICIES = [
    {"policy": "astra-script", "family": "LLM-written policy code", "model": "gpt-6-astra",
     "task": "peg-in-hole, UR5e", "sim": "mujoco", "local_box": local_box(),
     "local_csv": "results/local.csv", "deploy_csv": "results/deploy.csv",
     "notes": "Astra writes policy.py once (results/policies/v1.py); it runs unchanged on every trial."},
    {"policy": "astra-live", "family": "LLM closed-loop control", "model": "gpt-6-astra",
     "task": DITTO_TASK, "sim": "ditto", "local_box": DITTO_LOCAL_BOX,
     "notes": "Astra drives the arm live, one decision per step, 30 Hz control, 450-step budget, "
              "25-decision cap. Nominal placement only; local-only row."},
    {"policy": "molmoact2", "family": "VLA", "model": "MolmoAct2-DROID", "task": DITTO_TASK, "sim": "ditto",
     "local_box": DITTO_LOCAL_BOX, "notes": "Native MolmoAct2-DROID checkpoint, 15 Hz, 450 steps."},
    {"policy": "pi05", "family": "VLA", "model": "pi0.5-DROID", "task": DITTO_TASK, "sim": "ditto",
     "local_box": DITTO_LOCAL_BOX, "notes": "Native pi0.5-DROID, 450 steps."},
    {"policy": "gemini-robotics", "family": "VLA", "model": "Gemini Robotics", "task": None, "sim": None,
     "notes": "planned"},
    {"policy": "gr00t", "family": "VLA", "model": "GR00T", "task": None, "sim": None,
     "notes": "planned"},
]
KEYS = ["policy", "family", "model", "task", "sim", "status", "n_local", "local_success", "n_deploy",
        "deploy_success", "outside_success", "local_csv", "deploy_csv", "notes"]


def _find_csv(row: dict, tag: str) -> str | None:
    """Explicit path if given, else results/<sim>_<policy>_<tag>.csv (policy with - or _)."""
    if row.get(f"{tag}_csv"):
        return row[f"{tag}_csv"] if (ROOT / row[f"{tag}_csv"]).exists() else None
    names = {row["policy"], row["policy"].replace("-", "_")}
    sims = [row["sim"]] if row["sim"] else ["*"]
    hits = sorted({p for s in sims for n in names for p in RESULTS.glob(f"{s}_{n}_{tag}.csv")})
    if len(hits) > 1:
        print(f"WARNING {row['policy']} {tag}: several CSVs {[h.name for h in hits]}; using {hits[0].name}",
              file=sys.stderr)
    return str(hits[0].relative_to(ROOT)) if hits else None


def _rows(path: str | None) -> pd.DataFrame | None:
    if not path:
        return None
    df = pd.read_csv(ROOT / path)
    df["failure_mode"] = df["failure_mode"].fillna("")
    return _drop_infra(first_pass(df))


def _rate(df: pd.DataFrame | None) -> float | None:
    return round(float(_success(df).mean()), 4) if df is not None and len(df) else None


def build_row(meta: dict) -> dict:
    local_csv, deploy_csv = _find_csv(meta, "local"), _find_csv(meta, "deploy")
    local, deploy = _rows(local_csv), _rows(deploy_csv)
    n_local = 0 if local is None else len(local)
    n_deploy = 0 if deploy is None else len(deploy)
    outside = None
    if n_deploy:
        # Same rule as coverage_report: outside the local box over its task-relevant params, yaw folded.
        outside = _rate(deploy[~inside_local(deploy, meta.get("local_box") or local_box())])
    status = "full" if n_local and n_deploy else "smoke" if n_local or n_deploy else "planned"
    row = {**meta, "status": status, "n_local": n_local, "local_success": _rate(local),
           "n_deploy": n_deploy, "deploy_success": _rate(deploy), "outside_success": outside,
           "local_csv": local_csv, "deploy_csv": deploy_csv}
    return {k: row.get(k) for k in KEYS}


def main() -> None:
    rows = [build_row(m) for m in POLICIES]
    OUT.write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n")
    for r in rows:
        fmt = lambda x: "null" if x is None else f"{x:.1%}"
        print(f"{r['policy']:<16} {r['status']:<8} local {r['n_local']:>3} {fmt(r['local_success']):>6}   "
              f"deploy {r['n_deploy']:>3} {fmt(r['deploy_success']):>6}   outside {fmt(r['outside_success']):>6}")
    print(f"wrote {OUT.relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
