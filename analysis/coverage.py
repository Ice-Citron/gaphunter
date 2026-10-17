"""Coverage analysis: how much of the deployment domain the local benchmark covers,
and where the policy fails outside it. STUB — placeholder values until wired."""

from __future__ import annotations


def coverage_report(local_df, deploy_df, local_box, deploy_box) -> dict:
    return {
        "coverage_fraction": 0.0,
        "local_success": 0.0,
        "deploy_success": 0.0,
        "outside_local_success": 0.0,
        "gap_regions": [],
        "text": "Coverage report not computed yet.",
    }


def heatmap(df, x="dx", y="dy", local_box=None, path="results/heatmap.png") -> str:
    return path
