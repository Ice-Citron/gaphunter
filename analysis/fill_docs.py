"""Fill the {placeholders} in README.md and VIDEO_SCRIPT.md from results/local.csv + deploy.csv.

    python -m analysis.fill_docs            # real CSVs, edits files in place
    python -m analysis.fill_docs --fake     # fake CSVs, prints only (never writes fake numbers)
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from analysis.coverage import coverage_report, default_boxes

ROOT = Path(__file__).resolve().parents[1]
DOCS = ("README.md", "VIDEO_SCRIPT.md")


def values(local_csv: Path, deploy_csv: Path) -> dict:
    lb, db = default_boxes()
    r = coverage_report(pd.read_csv(local_csv), pd.read_csv(deploy_csv), lb, db)
    return {
        "{local_success}": f"{r['local_success']:.0%}",
        "{deploy_success}": f"{r['deploy_success']:.0%}",
        "{outside_success}": f"{r['outside_local_success']:.0%}",
        "{n_local}": str(r["n_local"]),
        "{n_deploy}": str(r["n_deploy"]),
        "{n_outside}": str(r["n_outside"]),
        "{coverage}": f"{r['coverage_fraction']:.1%}",
        "{coverage_all}": f"{r['coverage_fraction_all_params']:.1%}",
        "{gap_paragraph}": r["text"],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fake", action="store_true")
    a = ap.parse_args()
    prefix = "fake_" if a.fake else ""
    vals = values(ROOT / f"results/{prefix}local.csv", ROOT / f"results/{prefix}deploy.csv")
    for k, v in vals.items():
        print(f"{k:20} {v}")
    for name in DOCS:
        path = ROOT / name
        s = path.read_text()
        for k, v in vals.items():
            s = s.replace(k, v)
        left = [k for k in vals if k in s]
        if a.fake:
            print(f"{name}: dry run, {sum(path.read_text().count(k) for k in vals)} placeholders")
        else:
            path.write_text(s)
            print(f"{name}: filled" + (f", still has {left}" if left else ""))


if __name__ == "__main__":
    main()
