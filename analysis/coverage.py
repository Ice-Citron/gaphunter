"""Coverage analysis: how much of the deployment domain the local benchmark covers,
and where the policy fails outside it."""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

PARAMS = ("dx", "dy", "yaw")
UNITS = {"dx": "m", "dy": "m", "yaw": "deg"}

# Spec defaults, used only when runner.sample is not importable.
_LOCAL_BOX = {"dx": (-0.05, 0.05), "dy": (-0.05, 0.05), "yaw": (-15.0, 15.0)}
_DEPLOY_BOX = {"dx": (-0.20, 0.20), "dy": (-0.20, 0.20), "yaw": (-90.0, 90.0)}

# Dark surface shared with the Streamlit page.
BG = "#0e1117"
INK = "#e6e6e6"
MUTED = "#8b8f98"


def default_boxes() -> tuple[dict, dict]:
    try:
        from runner.sample import deploy_box, local_box
        return local_box(), deploy_box()
    except Exception:
        return dict(_LOCAL_BOX), dict(_DEPLOY_BOX)


def _range(box: dict, p: str) -> tuple[float, float]:
    """Accepts (lo, hi), [lo, hi] or {"lo":..,"hi":..} / {"min":..,"max":..}."""
    r = box[p]
    if isinstance(r, dict):
        lo = r.get("lo", r.get("min", r.get("low")))
        hi = r.get("hi", r.get("max", r.get("high")))
    else:
        lo, hi = r
    return float(lo), float(hi)


def _volume(box: dict) -> float:
    v = 1.0
    for p in PARAMS:
        lo, hi = _range(box, p)
        v *= hi - lo
    return v


def _inside(df: pd.DataFrame, box: dict) -> pd.Series:
    m = pd.Series(True, index=df.index)
    for p in PARAMS:
        lo, hi = _range(box, p)
        m &= df[p].between(lo, hi)
    return m


def _success(df: pd.DataFrame) -> pd.Series:
    s = df["success"]
    if s.dtype == object:
        s = s.astype(str).str.lower().isin(("true", "1", "yes"))
    return s.astype(float)


def _fmt(p: str, v: float) -> str:
    return f"{v:.0f}°" if p == "yaw" else f"{v:+.2f}"


def _pct(x: float) -> str:
    return "n/a" if x is None or np.isnan(x) else f"{x:.0%}"


def gap_regions(deploy_df, local_box, deploy_box, bins=6, max_success=0.5, min_n=5) -> list[dict]:
    succ = _success(deploy_df)
    out = []
    for p in PARAMS:
        dlo, dhi = _range(deploy_box, p)
        llo, lhi = _range(local_box, p)
        edges = np.linspace(dlo, dhi, bins + 1)
        idx = np.clip(np.digitize(deploy_df[p], edges) - 1, 0, bins - 1)
        for i in range(bins):
            lo, hi = edges[i], edges[i + 1]
            if not (hi <= llo or lo >= lhi):  # bin overlaps the local range
                continue
            sel = idx == i
            n = int(sel.sum())
            if n < min_n:
                continue
            rate = float(succ[sel].mean())
            if rate < max_success:
                out.append({"param": p, "range": (round(float(lo), 3), round(float(hi), 3)),
                            "success": rate, "n": n})
    return sorted(out, key=lambda g: (g["success"], -g["n"]))


def coverage_report(local_df, deploy_df, local_box=None, deploy_box=None) -> dict:
    if local_box is None or deploy_box is None:
        lb, db = default_boxes()
        local_box, deploy_box = local_box or lb, deploy_box or db

    cov = _volume(local_box) / _volume(deploy_box)
    local = float(_success(local_df).mean()) if len(local_df) else float("nan")
    deploy = float(_success(deploy_df).mean()) if len(deploy_df) else float("nan")
    outside_mask = ~_inside(deploy_df, local_box)
    outside = float(_success(deploy_df[outside_mask]).mean()) if outside_mask.any() else float("nan")
    gaps = gap_regions(deploy_df, local_box, deploy_box)

    if gaps:
        where = "; ".join(
            f"{g['param']} ∈ [{_fmt(g['param'], g['range'][0])}, {_fmt(g['param'], g['range'][1])}]"
            f"{' m' if UNITS[g['param']] == 'm' else ''} ({g['success']:.0%}, n={g['n']})"
            for g in gaps[:4]
        )
    else:
        where = "no single-parameter band with n ≥ 5 falls below 50%"

    text = (
        f"The local benchmark covers {cov:.1%} of the deployment domain by volume. "
        f"The policy succeeds on {_pct(local)} of local trials (n={len(local_df)}) and "
        f"{_pct(deploy)} of deployment trials (n={len(deploy_df)}); outside the local box it succeeds on "
        f"{_pct(outside)} (n={int(outside_mask.sum())}). Failures concentrate in: {where}. "
        f"A benchmark that stopped at the local box would have reported {_pct(local)} and shipped."
    )
    return {
        "coverage_fraction": cov,
        "local_success": local,
        "deploy_success": deploy,
        "outside_local_success": outside,
        "n_local": len(local_df),
        "n_deploy": len(deploy_df),
        "n_outside": int(outside_mask.sum()),
        "gap_regions": gaps,
        "text": text,
    }


def _cmap():
    from matplotlib.colors import LinearSegmentedColormap
    # red -> neutral grey -> green; the midpoint carries no hue.
    return LinearSegmentedColormap.from_list("gap", ["#d64545", "#6b6f78", "#2fb36a"])


def heatmap(df, x="dx", y="dy", local_box=None, path="results/heatmap.png", deploy_box=None,
            bins=8, yaw_bins=6) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    lb, db = default_boxes()
    local_box = local_box or lb
    deploy_box = deploy_box or db
    cmap = _cmap()
    succ = _success(df).to_numpy()

    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(1600 / 150, 800 / 150), dpi=150,
                                  gridspec_kw={"width_ratios": [1.15, 1]})
    fig.patch.set_facecolor(BG)
    for a in (ax, ax2):
        a.set_facecolor(BG)
        a.tick_params(colors=MUTED, labelsize=7)
        for s in a.spines.values():
            s.set_color("#30343c")

    # --- 2-D success grid over the deployment box ---
    xlo, xhi = _range(deploy_box, x)
    ylo, yhi = _range(deploy_box, y)
    xe = np.linspace(xlo, xhi, bins + 1)
    ye = np.linspace(ylo, yhi, bins + 1)
    xi = np.clip(np.digitize(df[x], xe) - 1, 0, bins - 1)
    yi = np.clip(np.digitize(df[y], ye) - 1, 0, bins - 1)
    n = np.zeros((bins, bins))
    k = np.zeros((bins, bins))
    np.add.at(n, (yi, xi), 1)
    np.add.at(k, (yi, xi), succ)
    with np.errstate(invalid="ignore", divide="ignore"):
        rate = np.where(n > 0, k / n, np.nan)

    cm = cmap.copy()
    cm.set_bad("#1a1d24")
    im = ax.pcolormesh(xe, ye, np.ma.masked_invalid(rate), cmap=cm, vmin=0, vmax=1,
                       edgecolors=BG, linewidth=1.5)
    for r in range(bins):
        for c in range(bins):
            if n[r, c] >= 2:
                ax.text((xe[c] + xe[c + 1]) / 2, (ye[r] + ye[r + 1]) / 2, f"{rate[r, c]:.0%}",
                        ha="center", va="center", fontsize=6.5, color="white")
    llx, lhx = _range(local_box, x)
    lly, lhy = _range(local_box, y)
    ax.add_patch(Rectangle((llx, lly), lhx - llx, lhy - lly, fill=False, edgecolor="white",
                           linestyle=(0, (4, 3)), linewidth=1.8))
    ax.text(llx, lhy, " local benchmark", color="white", fontsize=7, va="bottom", ha="left")
    ax.set_xlim(xlo, xhi)
    ax.set_ylim(ylo, yhi)
    ax.set_aspect("equal")
    ax.set_xlabel(f"{x} offset (m)", color=INK, fontsize=8)
    ax.set_ylabel(f"{y} offset (m)", color=INK, fontsize=8)
    ax.set_title("Success rate, Astra policy — deployment domain", color=INK, fontsize=10, loc="left")
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03)
    cb.ax.tick_params(colors=MUTED, labelsize=7)
    cb.outline.set_edgecolor("#30343c")
    cb.set_ticks([0, 0.5, 1])
    cb.set_ticklabels(["0%", "50%", "100%"])

    # --- 1-D marginal over yaw ---
    wlo, whi = _range(deploy_box, "yaw")
    we = np.linspace(wlo, whi, yaw_bins + 1)
    wi = np.clip(np.digitize(df["yaw"], we) - 1, 0, yaw_bins - 1)
    wn = np.bincount(wi, minlength=yaw_bins)
    wk = np.bincount(wi, weights=succ, minlength=yaw_bins)
    with np.errstate(invalid="ignore", divide="ignore"):
        wr = np.where(wn > 0, wk / wn, 0.0)
    centers = (we[:-1] + we[1:]) / 2
    width = (we[1] - we[0]) * 0.86
    ax2.bar(centers, wr, width=width, color=[cmap(v) for v in wr], edgecolor=BG, linewidth=1.5)
    for cx, v, cnt in zip(centers, wr, wn):
        if cnt:
            ax2.text(cx, v + 0.02, f"{v:.0%}\nn={cnt}", ha="center", va="bottom", fontsize=6.5, color=INK)
    llw, lhw = _range(local_box, "yaw")
    ax2.axvspan(llw, lhw, facecolor="white", alpha=0.06, edgecolor="white", linestyle=(0, (4, 3)),
                linewidth=1.2)
    ax2.text((llw + lhw) / 2, 1.13, "local", color="white", fontsize=7, ha="center")
    ax2.set_xlim(wlo, whi)
    ax2.set_ylim(0, 1.2)
    ax2.set_yticks([0, 0.5, 1])
    ax2.set_yticklabels(["0%", "50%", "100%"])
    ax2.set_xlabel("yaw offset (deg)", color=INK, fontsize=8)
    ax2.set_title("Success rate by yaw", color=INK, fontsize=10, loc="left")
    ax2.grid(axis="y", color="#30343c", linewidth=0.6)
    ax2.set_axisbelow(True)

    fig.tight_layout()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fig.savefig(path, dpi=150, facecolor=BG)
    plt.close(fig)
    return path


if __name__ == "__main__":
    import sys

    loc = sys.argv[1] if len(sys.argv) > 1 else "results/local.csv"
    dep = sys.argv[2] if len(sys.argv) > 2 else "results/deploy.csv"
    ldf, ddf = pd.read_csv(loc), pd.read_csv(dep)
    lb, db = default_boxes()
    rep = coverage_report(ldf, ddf, lb, db)
    print(rep["text"])
    print(heatmap(pd.concat([ldf, ddf], ignore_index=True), local_box=lb, deploy_box=db))
