"""Coverage analysis: how much of the deployment domain the local benchmark covers,
and where the policy fails outside it."""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

PARAMS = ("dx", "dy", "yaw")
UNITS = {"dx": "m", "dy": "m", "yaw": "deg", "r": "m"}
# Parameters that change the task. The square peg makes yaw matter.
ACTIVE_PARAMS = ("dx", "dy", "yaw")
# Lateral search range of the Astra-written policy v1 (0.6 mm grid, 3 rings): results/policies/v1.py.
SEARCH_RANGE_MM = 1.8
# The square peg looks the same every 90°, so yaw is folded into [-45, 45). None disables folding.
YAW_PERIOD = 90.0

# Spec defaults, used only when runner.sample is not importable.
_LOCAL_BOX = {"dx": (-0.05, 0.05), "dy": (-0.05, 0.05), "yaw": (-15.0, 15.0)}
_DEPLOY_BOX = {"dx": (-0.20, 0.20), "dy": (-0.20, 0.20), "yaw": (-90.0, 90.0)}

# Dark surface shared with the Streamlit page.
BG = "#0e1117"
INK = "#e6e6e6"
MUTED = "#8b8f98"
# The one accent: reserved for the outside-box number, the local-box rectangle and the search-range line.
ACCENT = "#ff5a3c"


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


def fold_yaw(df: pd.DataFrame) -> pd.DataFrame:
    if not YAW_PERIOD or "yaw" not in df:
        return df
    df = df.copy()
    df["yaw"] = (df["yaw"] + YAW_PERIOD / 2) % YAW_PERIOD - YAW_PERIOD / 2
    return df


def fold_box(box: dict) -> dict:
    """Clip the yaw range to one symmetry period: the distinct orientations the box contains."""
    if not YAW_PERIOD or "yaw" not in box:
        return box
    lo, hi = _range(box, "yaw")
    if hi - lo >= YAW_PERIOD:
        lo, hi = -YAW_PERIOD / 2, YAW_PERIOD / 2
    return {**box, "yaw": (max(lo, -YAW_PERIOD / 2), min(hi, YAW_PERIOD / 2))}


def inside_local(df: pd.DataFrame, local_box: dict, params=ACTIVE_PARAMS) -> pd.Series:
    """True for rows inside the local box over the task-relevant params, yaw folded."""
    return _inside(fold_yaw(df), fold_box(local_box), params)


def _volume(box: dict, params=PARAMS) -> float:
    v = 1.0
    for p in params:
        lo, hi = _range(box, p)
        v *= hi - lo
    return v


def _inside(df: pd.DataFrame, box: dict, params=PARAMS) -> pd.Series:
    m = pd.Series(True, index=df.index)
    for p in params:
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


def gap_regions(deploy_df, local_box, deploy_box, bins=6, max_success=0.5, min_n=5,
                params=PARAMS) -> list[dict]:
    succ = _success(deploy_df)
    out = []
    for p in params:
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


def first_pass(df: pd.DataFrame) -> pd.DataFrame:
    """Rows from the uniform Sobol pass. runner.refine adds pass=2 rows in uncertain cells; they are not
    uniform over the box, so rates over the box use pass 1 only. A missing `pass` column or value
    (e.g. Re-run rows) counts as pass 1."""
    return df[df["pass"].fillna(1) == 1] if "pass" in df else df


def _drop_infra(df: pd.DataFrame) -> pd.DataFrame:
    """api_error rows are infrastructure failures, not policy failures."""
    if "failure_mode" not in df:
        return df
    return df[df["failure_mode"].fillna("").astype(str) != "api_error"]


def coverage_report(local_df, deploy_df, local_box=None, deploy_box=None, params=ACTIVE_PARAMS) -> dict:
    """Coverage, "outside the local box" and gap regions use only `params`, the ones that change the task."""
    if local_box is None or deploy_box is None:
        lb, db = default_boxes()
        local_box, deploy_box = local_box or lb, deploy_box or db
    local_df, deploy_df = first_pass(local_df), first_pass(deploy_df)
    n_infra = len(local_df) + len(deploy_df)
    local_df, deploy_df = _drop_infra(local_df), _drop_infra(deploy_df)
    n_infra -= len(local_df) + len(deploy_df)

    cov_all = _volume(local_box) / _volume(deploy_box)  # raw 3-D box ratio, no folding
    folded = "yaw" in params and bool(YAW_PERIOD)
    if folded:
        local_df, deploy_df = fold_yaw(local_df), fold_yaw(deploy_df)
        local_box, deploy_box = fold_box(local_box), fold_box(deploy_box)
    cov = _volume(local_box, params) / _volume(deploy_box, params)
    local = float(_success(local_df).mean()) if len(local_df) else float("nan")
    deploy = float(_success(deploy_df).mean()) if len(deploy_df) else float("nan")
    outside_mask = ~_inside(deploy_df, local_box, params)
    outside = float(_success(deploy_df[outside_mask]).mean()) if outside_mask.any() else float("nan")
    gaps = gap_regions(deploy_df, local_box, deploy_box, params=params)

    if gaps:
        where = "; ".join(
            f"{g['param']} ∈ [{_fmt(g['param'], g['range'][0])}, {_fmt(g['param'], g['range'][1])}]"
            f"{' m' if UNITS[g['param']] == 'm' else ''} ({g['success']:.0%}, n={g['n']})"
            for g in gaps[:4]
        )
    else:
        where = "no single-parameter band with n ≥ 5 falls below 50%"

    dims = " × ".join(params)
    measure = {1: "length", 2: "area"}.get(len(params), "volume")
    ignored = [p for p in PARAMS if p not in params]
    text = (
        f"The local benchmark covers {cov:.1%} of the deployment domain by {measure} ({dims}"
        f"{'; ' + ', '.join(ignored) + ' has no effect on this task' if ignored else ''}"
        f"{f'; yaw folded to ±{YAW_PERIOD / 2:.0f}° by the peg symmetry' if folded else ''}). "
        f"The policy succeeds on {_pct(local)} of local trials (n={len(local_df)}) and "
        f"{_pct(deploy)} of deployment trials (n={len(deploy_df)}); outside the local box it succeeds on "
        f"{_pct(outside)} (n={int(outside_mask.sum())}). Failures concentrate in: {where}. "
        f"A benchmark that stopped at the local box would have reported {_pct(local)} and shipped."
    )
    if n_infra:
        text += f" ({n_infra} trials with API errors are excluded.)"
    return {
        "coverage_fraction": cov,
        "coverage_fraction_all_params": cov_all,
        "coverage_params": list(params),
        "local_success": local,
        "deploy_success": deploy,
        "outside_local_success": outside,
        "n_local": len(local_df),
        "n_deploy": len(deploy_df),
        "n_outside": int(outside_mask.sum()),
        "n_api_error": n_infra,
        "gap_regions": gaps,
        "text": text,
    }


def _cmap():
    from matplotlib.colors import LinearSegmentedColormap
    # Neutral sequential: 0% sits near the surface, 100% is light. Colour is kept for the accent only.
    return LinearSegmentedColormap.from_list("gap", ["#25282f", "#5d6169", "#d9dce1"])


def _error_panel(ax, df, succ, cmap, col, search_mm, per_side=4) -> None:
    """Success rate vs perception error on a log axis, bins split at the search range."""
    import matplotlib.pyplot as plt
    ax.set_title("Success rate by perception error", color=INK, fontsize=12, loc="left")
    ax.set_xlabel("hole_pose() error (mm, log scale)", color=INK, fontsize=10)
    ax.set_ylim(0, 1.2)
    ax.set_yticks([0, 0.5, 1])
    ax.set_yticklabels(["0%", "50%", "100%"])
    ax.grid(axis="y", color="#30343c", linewidth=0.6)
    ax.set_axisbelow(True)
    err = pd.to_numeric(df[col], errors="coerce").to_numpy() if col in df else np.array([])
    ok = np.isfinite(err)
    if ok.sum() < 5:
        ax.set_xticks([])
        ax.text(0.5, 0.5, f"no `{col}` data for this policy", transform=ax.transAxes, ha="center",
                va="center", color=MUTED, fontsize=10)
        return
    err, s = np.clip(err[ok], 1e-3, None), succ[ok]
    lo, hi = max(err.min(), 0.02), err.max() * 1.001
    if lo < search_mm < hi:
        edges = np.concatenate([np.geomspace(lo, search_mm, per_side + 1),
                                np.geomspace(search_mm, hi, per_side + 1)[1:]])
    else:
        edges = np.geomspace(lo, hi, 2 * per_side + 1)
    idx = np.clip(np.digitize(err, edges) - 1, 0, len(edges) - 2)
    cnt = np.bincount(idx, minlength=len(edges) - 1)
    k = np.bincount(idx, weights=s, minlength=len(edges) - 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        rate = np.where(cnt > 0, k / cnt, 0.0)
    left, right = edges[:-1] * 1.04, edges[1:] / 1.04  # surface gap between bars on the log axis
    ax.bar(left, rate, width=right - left, align="edge", color=[cmap(v) for v in rate],
           edgecolor=BG, linewidth=0)
    for l_, r_, v, c in zip(left, right, rate, cnt):
        if c:
            ax.text(np.sqrt(l_ * r_), v + 0.02, f"{v:.0%}\nn={c}", ha="center", va="bottom", fontsize=8,
                    color=INK)
    ax.set_xscale("log")
    ax.set_xlim(edges[0], edges[-1])
    ticks = [t for t in (0.03, 0.1, 0.3, 1, 3, 10, 30) if edges[0] <= t <= edges[-1]]
    ax.set_xticks(ticks, [f"{t:g}" for t in ticks])
    ax.xaxis.set_minor_formatter(plt.NullFormatter())
    ax.axvline(search_mm, color=ACCENT, linestyle=(0, (4, 3)), linewidth=2)
    ax.text(search_mm * 1.06, 1.16, f"policy search range ({search_mm:g} mm)", color="white", fontsize=9,
            ha="left", va="top")


def heatmap(df, x="dx", y="dy", local_box=None, path="results/heatmap.png", deploy_box=None,
            bins=8, marginal="dy", marginal_bins=7, error_col="pose_error_mm",
            search_mm=SEARCH_RANGE_MM, policy="Astra policy") -> str:
    """2-D success grid over (x, y), a 1-D success marginal over `marginal`, and success vs the
    perception error `error_col` with the policy's search range marked. Uses all rows (both passes):
    each bin's rate is conditional on the bin, so the refinement pass sharpens it without biasing it."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    lb, db = default_boxes()
    local_box = local_box or lb
    deploy_box = deploy_box or db
    cmap = _cmap()
    df = _drop_infra(df).copy()
    df[["dx", "dy", "yaw"]] = df[["dx", "dy", "yaw"]].astype(float)  # concat with an empty frame gives object dtype
    df = fold_yaw(df)
    local_box, deploy_box = fold_box(local_box), fold_box(deploy_box)
    df = df.assign(r=np.hypot(df["dx"], df["dy"]))
    dxl, dxh = _range(deploy_box, "dx")
    dyl, dyh = _range(deploy_box, "dy")
    lxl, lxh = _range(local_box, "dx")
    lyl, lyh = _range(local_box, "dy")
    # r: distance from the nominal pose. "local" is the largest circle inside the local box.
    deploy_box = {**deploy_box, "r": (0.0, float(np.hypot(max(-dxl, dxh), max(-dyl, dyh))))}
    local_box = {**local_box, "r": (0.0, min(-lxl, lxh, -lyl, lyh))}
    succ = _success(df).to_numpy()

    fig, (ax, ax2, ax3) = plt.subplots(1, 3, figsize=(2400 / 150, 800 / 150), dpi=150,
                                       gridspec_kw={"width_ratios": [1.55, 1, 1]})
    fig.patch.set_facecolor(BG)
    for a in (ax, ax2, ax3):
        a.set_facecolor(BG)
        a.tick_params(colors=MUTED, labelsize=9)
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
                        ha="center", va="center", fontsize=9,
                        color=BG if rate[r, c] > 0.6 else INK)
    llx, lhx = _range(local_box, x)
    lly, lhy = _range(local_box, y)
    ax.add_patch(Rectangle((llx, lly), lhx - llx, lhy - lly, fill=False, edgecolor=ACCENT,
                           linestyle=(0, (4, 3)), linewidth=1.8))
    ax.text(llx, lhy, " local benchmark", color="white", fontsize=9, va="bottom", ha="left")
    ax.set_xlim(xlo, xhi)
    ax.set_ylim(ylo, yhi)
    ax.set_xlabel(f"{x} offset ({UNITS[x]})", color=INK, fontsize=10)
    ax.set_ylabel(f"{y} offset ({UNITS[y]})", color=INK, fontsize=10)
    ax.set_title(f"Success rate, {policy} — deployment domain", color=INK, fontsize=12, loc="left")
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03)
    cb.ax.tick_params(colors=MUTED, labelsize=9)
    cb.outline.set_edgecolor("#30343c")
    cb.set_ticks([0, 0.5, 1])
    cb.set_ticklabels(["0%", "50%", "100%"])

    # --- 1-D marginal ---
    m = marginal
    wlo, whi = _range(deploy_box, m)
    we = np.linspace(wlo, whi, marginal_bins + 1)
    wi = np.clip(np.digitize(df[m], we) - 1, 0, marginal_bins - 1)
    wn = np.bincount(wi, minlength=marginal_bins)
    wk = np.bincount(wi, weights=succ, minlength=marginal_bins)
    with np.errstate(invalid="ignore", divide="ignore"):
        wr = np.where(wn > 0, wk / wn, 0.0)
    centers = (we[:-1] + we[1:]) / 2
    width = (we[1] - we[0]) * 0.86
    ax2.bar(centers, wr, width=width, color=[cmap(v) for v in wr], edgecolor=BG, linewidth=1.5)
    for cx, v, cnt in zip(centers, wr, wn):
        if cnt:
            ax2.text(cx, v + 0.02, f"{v:.0%}\nn={cnt}", ha="center", va="bottom", fontsize=9, color=INK)
    llw, lhw = _range(local_box, m)
    ax2.axvspan(llw, lhw, facecolor="white", alpha=0.06, edgecolor="white", linestyle=(0, (4, 3)),
                linewidth=1.2)
    ax2.text((llw + lhw) / 2, 1.13, "local", color="white", fontsize=9, ha="center")
    ax2.set_xlim(wlo, whi)
    ax2.set_ylim(0, 1.2)
    ax2.set_yticks([0, 0.5, 1])
    ax2.set_yticklabels(["0%", "50%", "100%"])
    name = "distance from nominal pose" if m == "r" else f"{m} offset"
    ax2.set_xlabel(f"{name} ({UNITS[m]})", color=INK, fontsize=10)
    ax2.set_title("Success rate by distance from centre" if m == "r" else f"Success rate by {m}",
                  color=INK, fontsize=12, loc="left")
    ax2.grid(axis="y", color="#30343c", linewidth=0.6)
    ax2.set_axisbelow(True)

    _error_panel(ax3, df, succ, cmap, error_col, search_mm)

    fig.tight_layout()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    # Write then rename, so a concurrent reader (another Streamlit session) never sees a partial PNG.
    tmp = f"{path}.{os.getpid()}.tmp.png"
    fig.savefig(tmp, dpi=150, facecolor=BG)
    plt.close(fig)
    os.replace(tmp, path)
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


# --- policy comparison --------------------------------------------------------------------------------------
POLICY_COLUMNS = ["policy", "family", "task", "n local", "local success", "n deploy", "deploy success",
                  "outside-box success", "status"]
_NUMERIC = POLICY_COLUMNS[3:8]


def load_policies(path="results/policies.json", root=".") -> list[dict]:
    import json
    p = os.path.join(root, path)
    if not os.path.exists(p):
        return []
    data = json.load(open(p))
    return data["policies"] if isinstance(data, dict) else data


def _cell(k: int, n: int, smoke: bool) -> str:
    if n == 0:
        return "no trials"
    return f"{k}/{n} ({k / n:.0%})" if smoke else f"{k / n:.0%}"


def policy_row(pol: dict, root=".", local_box=None, deploy_box=None, warns: list | None = None) -> dict:
    """One table row. Planned rows say "planned" in every numeric cell, never a dash that could read as zero.
    Smoke rows carry their n inside each success cell. Numbers come from the row's CSVs; numbers stored in
    policies.json are used only when a CSV is missing, and are cross-checked otherwise."""
    status = str(pol.get("status") or "planned").lower()
    name = pol.get("policy") or pol.get("name") or pol.get("id") or "?"
    row = {"policy": name, "family": pol.get("family") or "", "task": pol.get("task") or "not chosen yet",
           "status": status, "id": name}
    if status == "planned":
        return {**row, **{c: "planned" for c in _NUMERIC}}

    def read(key):
        f = pol.get(key)
        if not f or not os.path.exists(os.path.join(root, f)):
            return None
        return pd.read_csv(os.path.join(root, f))

    ldf, ddf = read("local_csv"), read("deploy_csv")
    empty = pd.DataFrame(columns=["dx", "dy", "yaw", "success"])
    r = coverage_report(ldf if ldf is not None else empty, ddf if ddf is not None else empty,
                        local_box, deploy_box)
    stored = {"n_local": pol.get("n_local"), "local_success": pol.get("local_success"),
              "n_deploy": pol.get("n_deploy"), "deploy_success": pol.get("deploy_success"),
              "outside_local_success": pol.get("outside_success")}
    if warns is not None:
        for k, v in stored.items():
            have = ldf is not None if k in ("n_local", "local_success") else ddf is not None
            if have and v is not None and abs(float(v) - float(r[k])) > 0.0005:
                warns.append(f"policies.json {name}: {k} = {v} but the CSV gives {r[k]:.4f}")
    smoke = status == "smoke"
    k_of = lambda rate, n: int(round(rate * n)) if n else 0  # noqa: E731

    def cells(have, n, rate, n_stored, rate_stored):
        if not have:
            if n_stored and rate_stored is not None:  # no CSV, but the JSON carries the numbers
                n, rate = int(n_stored), float(rate_stored)
            else:
                return "not run", "not run"
        return str(n), _cell(k_of(rate, n), n, smoke)

    row["n local"], row["local success"] = cells(ldf is not None, r["n_local"], r["local_success"],
                                                 stored["n_local"], stored["local_success"])
    row["n deploy"], row["deploy success"] = cells(ddf is not None, r["n_deploy"], r["deploy_success"],
                                                   stored["n_deploy"], stored["deploy_success"])
    if ddf is not None:
        row["outside-box success"] = _cell(k_of(r["outside_local_success"], r["n_outside"]), r["n_outside"], smoke)
    elif stored["outside_local_success"] is not None:
        row["outside-box success"] = f"{float(stored['outside_local_success']):.0%}"
    else:
        row["outside-box success"] = "not run"
    return row


def policy_table(path="results/policies.json", root=".", local_box=None, deploy_box=None,
                 warns: list | None = None) -> pd.DataFrame:
    try:  # per-row local boxes (e.g. the reach-limited Ditto box) live in runner.policies, not in the JSON
        from runner.policies import POLICIES
        boxes = {m["policy"]: m["local_box"] for m in POLICIES if m.get("local_box")}
    except Exception:
        boxes = {}
    rows = [policy_row(p, root, boxes.get(p.get("policy"), local_box), deploy_box, warns)
            for p in load_policies(path, root)]
    return pd.DataFrame(rows, columns=POLICY_COLUMNS + ["id"])


def policy_table_markdown(table: pd.DataFrame) -> str:
    cols = POLICY_COLUMNS
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in table.iterrows():
        out.append("| " + " | ".join(str(r[c]).replace("|", "/") for c in cols) + " |")
    return "\n".join(out)


def policy_status_sentence(table: pd.DataFrame) -> str:
    words = {0: "none", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}
    c = table["status"].value_counts()
    n = lambda s: words.get(int(c.get(s, 0)), str(int(c.get(s, 0))))  # noqa: E731
    parts = [f"{n('full')} {'row is' if c.get('full', 0) == 1 else 'rows are'} full",
             f"{n('smoke')} {'is a' if c.get('smoke', 0) == 1 else 'are'} smoke {'run' if c.get('smoke', 0) == 1 else 'runs'}",
             "the rest are planned" if c.get("planned", 0) else "none are planned"]
    return f"Today {parts[0]}, {parts[1]}, and {parts[2]}."
