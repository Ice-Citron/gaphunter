"""Run a batch of trials across worker processes and save results/<tag>.csv.

    python -m runner.batch --box local  --n 30  --tag local  --workers 4
    python -m runner.batch --box deploy --n 100 --tag deploy --workers 4 --render-failures 4
    python -m runner.batch --tag deploy --summary          # summarise an existing CSV
"""
from __future__ import annotations

import argparse
import dataclasses
import multiprocessing as mp
import os
import random
import sys
import time
import traceback
from pathlib import Path

import pandas as pd

from runner.sample import deploy_box, local_box, sample_box

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
COLUMNS = ["dx", "dy", "yaw", "seed", "success", "failure_mode", "n_decisions", "t_wall", "clip", "transcript"]
SAVE_EVERY = 10

try:
    from tqdm import tqdm
except ImportError:  # tqdm is optional
    tqdm = None

_run_trial = None  # set per worker process by _init_worker


def _init_worker(force_fake: bool, jitter: float) -> None:
    """Import the sim inside the worker: sim objects can't be sent between processes."""
    global _run_trial
    if jitter > 0:
        time.sleep(random.random() * jitter)  # spread out the first Astra calls
    if not force_fake:
        try:
            from sim.trial import run_trial
            _run_trial = run_trial
            return
        except Exception:
            print("!" * 70 + f"\nWARNING runner.batch: sim.trial import failed in pid {os.getpid()}, "
                  "FALLING BACK TO FAKE SIM\n" + traceback.format_exc() + "!" * 70, file=sys.stderr)
    from runner.fake import fake_run_trial
    _run_trial = fake_run_trial


def _work(job: tuple[int, dict, bool]) -> tuple[int, dict]:
    i, params, render = job
    t0 = time.time()
    try:
        res = dataclasses.asdict(_run_trial(dict(params), render=render))
    except Exception:
        # A crash counts as a failed trial; the batch keeps going. "api_error" matches sim.trial's crash label.
        print(f"ERROR trial {i} {params}:\n{traceback.format_exc()}", file=sys.stderr)
        res = {"params": params, "success": False, "failure_mode": "api_error", "n_decisions": 0,
               "t_wall": time.time() - t0, "clip": None, "transcript": None}
    row = {k: params.get(k) for k in ("dx", "dy", "yaw", "seed")}
    row.update({k: res.get(k) for k in COLUMNS[4:]})
    return i, row


def _to_df(rows: dict[int, dict]) -> pd.DataFrame:
    df = pd.DataFrame([rows[i] for i in sorted(rows)], columns=COLUMNS)
    df["success"] = df["success"].astype(bool)
    df["failure_mode"] = df["failure_mode"].fillna("")
    df[["clip", "transcript"]] = df[["clip", "transcript"]].astype(object)
    return df


def _save(df: pd.DataFrame, tag: str) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"{tag}.csv"
    tmp = path.with_suffix(".csv.tmp")
    df.to_csv(tmp, index=False)
    tmp.replace(path)  # atomic, so the app never reads half a file
    return path


def _pick_failures(df: pd.DataFrame, k: int) -> list[int]:
    """Up to k failed row indices, round-robin across failure modes."""
    fails = df[~df["success"]]
    queues = {m: list(g.index) for m, g in sorted(fails.groupby("failure_mode"))}
    picked: list[int] = []
    while len(picked) < k and any(queues.values()):
        for q in queues.values():
            if q and len(picked) < k:
                picked.append(q.pop(0))
    return picked


def _render_failures(df: pd.DataFrame, k: int, force_fake: bool, tag: str) -> pd.DataFrame:
    candidates = _pick_failures(df, len(df))  # whole ranked list; take the first k that fail again
    done = 0
    with mp.get_context("spawn").Pool(1, initializer=_init_worker, initargs=(force_fake, 0.0)) as pool:
        for idx in candidates:
            if done >= k:
                break
            params = {c: float(df.at[idx, c]) for c in ("dx", "dy", "yaw")} | {"seed": int(df.at[idx, "seed"])}
            _, row = pool.apply(_work, ((idx, params, True),))
            if row["success"]:
                print(f"WARNING render re-run of row {idx} succeeded; skipping it", file=sys.stderr)
                continue
            df.at[idx, "clip"] = row["clip"]
            df.at[idx, "transcript"] = row["transcript"]
            done += 1
            print(f"rendered row {idx} ({df.at[idx, 'failure_mode']}): clip={row['clip']}")
            _save(df, tag)
    if done < k:
        print(f"WARNING rendered {done}/{k} failure clips", file=sys.stderr)
    return df


def run_batch(param_list, n_workers=4, render_failures=0, tag="run", force_fake=False, jitter=0.0,
              progress=None) -> pd.DataFrame:
    """progress(done, total) is called in the main process after each trial."""
    jobs = [(i, p, False) for i, p in enumerate(param_list)]
    rows: dict[int, dict] = {}
    bar = tqdm(total=len(jobs), desc=tag) if tqdm else None
    with mp.get_context("spawn").Pool(n_workers, initializer=_init_worker, initargs=(force_fake, jitter)) as pool:
        for i, row in pool.imap_unordered(_work, jobs):
            rows[i] = row
            if progress:
                progress(len(rows), len(jobs))
            if bar:
                bar.update(1)
            elif len(rows) % SAVE_EVERY == 0 or len(rows) == len(jobs):
                print(f"[{tag}] {len(rows)}/{len(jobs)}", file=sys.stderr)
            if len(rows) % SAVE_EVERY == 0:
                _save(_to_df(rows), tag)
    if bar:
        bar.close()
    df = _to_df(rows)
    _save(df, tag)
    if render_failures > 0:
        df = _render_failures(df, render_failures, force_fake, tag)
    return df


def summary(df: pd.DataFrame, tag: str = "") -> str:
    modes = df.loc[~df["success"], "failure_mode"].value_counts().sort_index()
    lines = [
        f"== {tag} ==",
        f"n               {len(df)}",
        f"success rate    {df['success'].mean():.1%} ({int(df['success'].sum())}/{len(df)})",
        "failure modes   " + (", ".join(f"{m}={c}" for m, c in modes.items()) or "none"),
        f"mean decisions  {df['n_decisions'].mean():.2f}",
        f"total wall time {df['t_wall'].sum():.1f} s (mean {df['t_wall'].mean():.2f} s/trial)",
        f"clips           {int(df['clip'].notna().sum())}",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--box", choices=["local", "deploy"], default="local")
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--tag", default=None, help="CSV name; defaults to --box")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--render-failures", type=int, default=0)
    ap.add_argument("--method", choices=["sobol", "uniform", "grid"], default="sobol")
    ap.add_argument("--seed", type=int, default=0, help="base seed; trial i gets seed + i")
    ap.add_argument("--fake", action="store_true", help="force runner.fake even if sim.trial imports")
    ap.add_argument("--jitter", type=float, default=0.0, help="max random sleep (s) at worker start")
    ap.add_argument("--summary", action="store_true", help="only summarise results/<tag>.csv; run nothing")
    a = ap.parse_args()
    tag = a.tag or a.box

    if a.summary:
        df = pd.read_csv(RESULTS / f"{tag}.csv")
        df["failure_mode"] = df["failure_mode"].fillna("")
        print(summary(df, tag))
        return

    box = local_box() if a.box == "local" else deploy_box()
    params = sample_box(box, a.n, method=a.method, seed=a.seed)
    t0 = time.time()
    df = run_batch(params, n_workers=a.workers, render_failures=a.render_failures, tag=tag,
                   force_fake=a.fake, jitter=a.jitter)
    print(summary(df, tag))
    print(f"elapsed         {time.time() - t0:.1f} s -> {RESULTS / f'{tag}.csv'}")


if __name__ == "__main__":
    main()
