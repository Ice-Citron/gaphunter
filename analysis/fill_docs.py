"""Render README.md and VIDEO_SCRIPT.md from docs/*.template.md with numbers from the result CSVs.

    python -m analysis.fill_docs            # real CSVs -> writes README.md, VIDEO_SCRIPT.md
    python -m analysis.fill_docs --fake     # fake CSVs, prints values and checks only, writes nothing

n comes from the CSVs. Boxes come from runner.sample (what the batch sampled), cross-checked against the
CSV extents and against sim/README.md; mismatches are printed as WARN lines, never silently fixed.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

from analysis.coverage import (_range, coverage_report, default_boxes, first_pass, policy_status_sentence,
                               policy_table, policy_table_markdown)

ROOT = Path(__file__).resolve().parents[1]
DOCS = ("README.md", "VIDEO_SCRIPT.md")
UNIT = {"dx": "m", "dy": "m", "yaw": "°"}


def box_text(box: dict, params=("dx", "dy", "yaw")) -> str:
    parts = []
    for p in params:
        lo, hi = _range(box, p)
        if p == "yaw":
            parts.append(f"{p} {lo:+.0f}…{hi:+.0f}°")
        else:
            parts.append(f"{p} {lo:+.2f}…{hi:+.2f} m")
    return ", ".join(parts)


def check_box(name: str, df: pd.DataFrame, box: dict) -> list[str]:
    """WARN if CSV rows fall outside the box, or span much less of it (box changed after the batch)."""
    warns = []
    for p in ("dx", "dy", "yaw"):
        if p not in df or df.empty:
            continue
        lo, hi = _range(box, p)
        eps = 1e-6 * max(1.0, hi - lo)
        out = int(((df[p] < lo - eps) | (df[p] > hi + eps)).sum())
        if out:
            warns.append(f"{name}: {out} rows have {p} outside the box [{lo}, {hi}]")
        span = (df[p].max() - df[p].min()) / (hi - lo) if hi > lo else 1.0
        if len(df) >= 10 and span < 0.8:
            warns.append(f"{name}: {p} spans only {span:.0%} of the box [{lo}, {hi}] "
                         f"(CSV {df[p].min():.3f}…{df[p].max():.3f}); was the box changed after the batch?")
    return warns


def check_sim_readme(box: dict) -> list[str]:
    path = ROOT / "sim" / "README.md"
    if not path.exists():
        return ["sim/README.md missing; deployment box not cross-checked"]
    text = path.read_text()
    warns = []
    for p in ("dx", "dy"):
        for v in _range(box, p):
            if not re.search(rf"(?<![\d.]){abs(v):.2f}".replace(".", r"\.") + r"(?!\d)", text):
                warns.append(f"sim/README.md does not mention deploy {p} bound {v:+.2f}")
    return warns


def values(local_csv: Path, deploy_csv: Path) -> tuple[dict, list[str]]:
    lb, db = default_boxes()
    ldf, ddf = pd.read_csv(local_csv), pd.read_csv(deploy_csv)
    r = coverage_report(ldf, ddf, lb, db)
    warns = check_box("local.csv", ldf, lb) + check_box("deploy.csv", ddf, db) + check_sim_readme(db)
    vals = {
        "{local_success}": f"{r['local_success']:.0%}",
        "{deploy_success}": f"{r['deploy_success']:.0%}",
        "{outside_success}": f"{r['outside_local_success']:.0%}",
        "{n_local}": str(r["n_local"]),
        "{n_deploy}": str(r["n_deploy"]),
        "{n_outside}": str(r["n_outside"]),
        "{rows_local}": str(len(first_pass(ldf))),
        "{rows_deploy}": str(len(first_pass(ddf))),  # the batch size; refine adds pass-2 rows
        "{coverage}": f"{r['coverage_fraction']:.1%}",
        "{coverage_all}": f"{r['coverage_fraction_all_params']:.1%}",
        "{local_box}": box_text(lb),
        "{deploy_box}": box_text(db),
        "{gap_paragraph}": r["text"],
    }
    table = policy_table("results/policies.json", root=str(ROOT), local_box=lb, deploy_box=db, warns=warns)
    if table.empty:
        warns.append("results/policies.json missing or empty; policy table falls back to the Astra v1 row from the CSVs")
        fallback = {"id": "astra-v1", "name": "Astra v1", "family": "LLM-written code",
                    "task": "MuJoCo UR5e peg-in-hole", "status": "full",
                    "local_csv": str(local_csv.relative_to(ROOT)), "deploy_csv": str(deploy_csv.relative_to(ROOT))}
        from analysis.coverage import POLICY_COLUMNS, policy_row
        table = pd.DataFrame([policy_row(fallback, str(ROOT), lb, db)], columns=POLICY_COLUMNS + ["id"])
    vals["{policy_table}"] = policy_table_markdown(table)
    vals["{policy_status}"] = policy_status_sentence(table)
    return vals, warns


def prose_words(md: str) -> int:
    """Words outside fenced code blocks and table rows (Shi Hao: code does not count; tables are data)."""
    words, in_code = 0, False
    for line in md.splitlines():
        if line.startswith("```"):
            in_code = not in_code
            continue
        if not in_code and not line.lstrip().startswith("|"):
            words += len(line.split())
    return words


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fake", action="store_true")
    a = ap.parse_args()
    prefix = "fake_" if a.fake else ""
    vals, warns = values(ROOT / f"results/{prefix}local.csv", ROOT / f"results/{prefix}deploy.csv")
    for k, v in vals.items():
        print(f"{k:18} {v if k != '{policy_table}' else chr(10) + v}")
    if not a.fake:  # the README image, from the committed CSVs only (never the app's session data)
        from analysis.coverage import heatmap
        lb, db = default_boxes()
        ldf = pd.read_csv(ROOT / "results/local.csv")
        ddf = pd.read_csv(ROOT / "results/deploy.csv")
        print("heatmap:", heatmap(pd.concat([ldf, ddf], ignore_index=True), local_box=lb, deploy_box=db,
                                  path=str(ROOT / "results/heatmap.png")))
    for w in warns:
        print(f"WARN {w}", file=sys.stderr)
    for name in DOCS:
        s = (ROOT / "docs" / f"{Path(name).stem}.template.md").read_text()
        for k, v in vals.items():
            s = s.replace(k, v)
        left = sorted(set(re.findall(r"\{[a-z_]+\}", s)))
        if a.fake:
            print(f"{name}: dry run" + (f", unfilled {left}" if left else ", all placeholders filled"))
        else:
            (ROOT / name).write_text(s)
            print(f"{name}: written" + (f", unfilled {left}" if left else ""))
        if name == "README.md":
            n = prose_words(s)
            print(f"README prose words (code blocks and tables excluded): {n}")
            if n > 500:
                print(f"WARN README prose is {n} words, over 500", file=sys.stderr)


if __name__ == "__main__":
    main()
