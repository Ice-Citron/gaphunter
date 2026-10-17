"""Refinement pass: add trials in the uncertain cells of the dx x dy heatmap grid.

    GAPHUNTER_SIM=mujoco python -m runner.refine --tag deploy --per-cell 10

Reads results/<tag>.csv and bins its pass-1 rows into the same bins x bins grid as
analysis.coverage.heatmap. Every cell with success in [lo, hi] or fewer than --min-n trials
gets --per-cell new Sobol points (dx, dy inside the cell; yaw over the whole box). The new rows
are appended to results/<tag>.csv with pass=2; any earlier pass-2 rows are replaced, so a
re-run gives the same file. Original rows get pass=1.

Pass-2 points are not uniform over the box: compute headline success rates on pass == 1 only.
"""
from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd

from runner.batch import COLUMNS, RESULTS, _save, run_batch, summary
from runner.sample import deploy_box, sample_box

SEED_BASE = 100_000  # pass-2 seeds never collide with pass-1 seeds (0..n-1)


def _cells(df: pd.DataFrame, box: dict, bins: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Per-cell trial counts and successes, binned exactly like analysis.coverage.heatmap."""
    xe = np.linspace(*box["dx"], bins + 1)
    ye = np.linspace(*box["dy"], bins + 1)
    xi = np.clip(np.digitize(df["dx"], xe) - 1, 0, bins - 1)
    yi = np.clip(np.digitize(df["dy"], ye) - 1, 0, bins - 1)
    n = np.zeros((bins, bins), dtype=int)
    k = np.zeros((bins, bins), dtype=int)
    np.add.at(n, (xi, yi), 1)
    np.add.at(k, (xi, yi), df["success"].astype(int).to_numpy())
    return n, k, xe, ye


def refine_params(df: pd.DataFrame, box: dict, per_cell: int, bins=8, lo=0.10, hi=0.90, min_n=5) -> list[dict]:
    n, k, xe, ye = _cells(df, box, bins)
    params: list[dict] = []
    for i in range(bins):
        for j in range(bins):
            rate = k[i, j] / n[i, j] if n[i, j] else None
            if n[i, j] >= min_n and not (lo <= rate <= hi):
                continue
            cell = {"dx": (xe[i], xe[i + 1]), "dy": (ye[j], ye[j + 1]), "yaw": box["yaw"]}
            params += sample_box(cell, per_cell, seed=SEED_BASE + (i * bins + j) * per_cell)
            print(f"cell dx[{xe[i]:+.3f},{xe[i+1]:+.3f}] dy[{ye[j]:+.3f},{ye[j+1]:+.3f}] "
                  f"n={n[i, j]} success={'-' if rate is None else f'{rate:.0%}'} -> +{per_cell}")
    return params


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", default="deploy")
    ap.add_argument("--per-cell", type=int, default=10)
    ap.add_argument("--bins", type=int, default=8)
    ap.add_argument("--lo", type=float, default=0.10)
    ap.add_argument("--hi", type=float, default=0.90)
    ap.add_argument("--min-n", type=int, default=5)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--fake", action="store_true", help="force runner.fake even if sim.trial imports")
    a = ap.parse_args()

    df = pd.read_csv(RESULTS / f"{a.tag}.csv")
    df["failure_mode"] = df["failure_mode"].fillna("")
    df["pass"] = df["pass"].fillna(1).astype(int) if "pass" in df else 1
    base = df[df["pass"] == 1].reset_index(drop=True).reindex(columns=COLUMNS)  # old CSVs lack pose_error_mm

    params = refine_params(base, deploy_box(), a.per_cell, a.bins, a.lo, a.hi, a.min_n)
    if not params:
        print("no cells need refinement")
        _save(base, a.tag)
        return
    extra = run_batch(params, n_workers=a.workers, tag=f"{a.tag}_refine", force_fake=a.fake)
    extra["pass"] = 2
    out = pd.concat([base, extra], ignore_index=True)[COLUMNS]
    _save(out, a.tag)
    (RESULTS / f"{a.tag}_refine.csv").unlink(missing_ok=True)  # merged; drop the crash-recovery copy

    print(summary(base, f"{a.tag} pass 1"))
    print(summary(extra, f"{a.tag} pass 2 ({len(params) // a.per_cell} cells x {a.per_cell})"))
    print(f"wrote {len(out)} rows -> {RESULTS / f'{a.tag}.csv'}", file=sys.stderr)


if __name__ == "__main__":
    main()
