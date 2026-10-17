"""GapHunter — one dark page: where the benchmark stopped and the failures start."""

from __future__ import annotations

import html
import importlib
import inspect
import json
import os
import random
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
RESULTS = ROOT / "results"

import analysis.coverage  # noqa: E402
import runner.sample  # noqa: E402

# Streamlit reruns this script but keeps imported modules; reload so edits to the analysis show up.
# runner.sample first: it defines the boxes that analysis.coverage reads.
importlib.reload(runner.sample)
importlib.reload(analysis.coverage)
from analysis.coverage import (coverage_report, default_boxes, heatmap, inside_local, load_policies,  # noqa: E402
                               policy_table)

st.set_page_config(page_title="GapHunter", layout="wide", initial_sidebar_state="collapsed")

st.markdown(
    """
<style>
[data-testid="stSidebar"], [data-testid="collapsedControl"] {display: none;}
.block-container {padding-top: 1rem; padding-bottom: 1rem; max-width: 1280px;}
h1 {margin-bottom: 0 !important; font-size: 2.3rem !important; padding-top: 0 !important;}
p.gh-sub, .stMarkdown p.gh-sub {color: #8b8f98; font-size: 1rem !important; margin: 0 0 .7rem 0;}
.gh-pull {color: #e6e6e6; font-size: 1.3rem; line-height: 1.4; border-left: 3px solid #5d6169;
          padding: .05rem 0 .05rem 1rem; margin: 0 0 .5rem 0;}
.gh-pull b {font-size: 1.55rem;}
.gh-pull span {color: #8b8f98; font-size: 1rem;}
.gh-tile .lbl {color: #8b8f98; font-size: .8rem; text-transform: uppercase; letter-spacing: .04em;}
.gh-tile .val {font-size: 2rem; font-weight: 600; line-height: 1.1; color: #c3c7cf;}
.gh-tile.hero .val {font-size: 3.4rem; font-weight: 700;}
.gh-tile .val.none {font-size: 1.6rem !important; color: #5d6169;}
.gh-tile .n {color: #8b8f98; font-size: .8rem;}
.gh-ph {background: #2a2d34; color: #8b8f98; border-radius: 8px; height: 170px;
        display: flex; align-items: center; justify-content: center; text-align: center; padding: 1rem;}
.gh-report {font-size: 1rem; line-height: 1.55;}
p.gh-src, .stMarkdown p.gh-src {color: #8b8f98; font-size: .75rem !important; margin: 0 0 .3rem 0;}
.gh-foot {color: #8b8f98; font-size: .85rem; padding-top: .6rem; margin-top: .8rem;}
video {max-height: 170px;}
.gh-badge {color: #e6e6e6; background: #30343c; font-weight: 600; border-radius: 4px; padding: 0 .35rem; font-size: .75rem;}
.gh-cap {color: #8b8f98; font-size: .8rem; line-height: 1.5;}
.gh-head {color: #e6e6e6; font-size: .95rem; margin: .3rem 0 .5rem 0;}
.gh-quote {color: #e6e6e6; font-style: italic; margin: 0 0 .6rem 0; padding: 0;}
.gh-quote span {color: #8b8f98; font-size: .8rem;}
h3 {padding: .4rem 0 .3rem 0 !important;}
table.gh-pt {width: 100%; border-collapse: collapse; font-size: .78rem; margin: 0 0 .1rem 0;}
table.gh-pt th {color: #8b8f98; font-weight: 500; text-align: left; padding: .05rem .5rem; border: 0; border-bottom: 1px solid #30343c;}
table.gh-pt td {color: #c3c7cf; padding: .05rem .5rem; border: 0;}
table.gh-pt tr {border: 0;}
table.gh-pt td.num {text-align: right; font-variant-numeric: tabular-nums;}
table.gh-pt tr.planned td {color: #4a4e56;}
table.gh-pt tr.sel td {color: #e6e6e6; font-weight: 600; background: #1a1d24;}
</style>
""",
    unsafe_allow_html=True,
)

from analysis.coverage import ACCENT  # noqa: E402  the one accent colour; everything else is neutral


def _badge(mode: str) -> str:
    return f'<span class="gh-badge">{html.escape(mode or "success")}</span>'


def placeholder(msg: str) -> None:
    st.markdown(f'<div class="gh-ph">{html.escape(msg)}</div>', unsafe_allow_html=True)


def _mtime(p: Path) -> float:
    return p.stat().st_mtime if p.exists() else 0.0


def _resolve(p) -> Path | None:
    if p is None or (isinstance(p, float) and pd.isna(p)) or str(p).strip() in ("", "nan", "None"):
        return None
    path = Path(str(p))
    path = path if path.is_absolute() else ROOT / path
    return path if path.exists() else None


@st.cache_data
def _read_csv(path: str, mtime: float) -> pd.DataFrame:
    return pd.read_csv(path)


@st.cache_data
def _fake_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    from runner.fake import fake_run_trial
    from runner.sample import sample_box

    lb, db = default_boxes()

    def run(ps):
        rows = []
        for p in ps:
            r = fake_run_trial(p)
            rows.append({**p, "success": r.success, "failure_mode": r.failure_mode,
                         "n_decisions": r.n_decisions, "t_wall": r.t_wall, "clip": r.clip,
                         "transcript": r.transcript})
        return pd.DataFrame(rows)

    return run(sample_box(lb, 30, seed=0)), run(sample_box(db, 100, seed=1000))


def load_data() -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Real CSVs first, then the fake CSVs, then fake data generated in-process."""
    for loc, dep, src in (("local.csv", "deploy.csv", "real"),
                          ("fake_local.csv", "fake_deploy.csv", "fake (CSV)")):
        lp, dp = RESULTS / loc, RESULTS / dep
        if lp.exists() and dp.exists():
            try:
                return _read_csv(str(lp), _mtime(lp)), _read_csv(str(dp), _mtime(dp)), src
            except Exception:
                pass
    try:
        l, d = _fake_data()
        return l, d, "fake (generated)"
    except Exception:
        empty = pd.DataFrame(columns=["dx", "dy", "yaw", "seed", "success", "failure_mode",
                                      "n_decisions", "t_wall", "clip", "transcript"])
        return empty, empty.copy(), "none"


@st.cache_data
def _heatmap_png(df: pd.DataFrame, path: str, code_mtime: float, lb: dict, db: dict) -> bytes | None:
    heatmap(df, local_box=lb, deploy_box=db, path=path)
    return Path(path).read_bytes()


@st.cache_data
def _transcript(path: str, mtime: float):
    with open(path) as f:
        return json.load(f)


def _featured() -> dict:
    p = RESULTS / "featured.json"
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except Exception:
        return {}


def pick_clip(df: pd.DataFrame, want_success: bool, box: dict) -> dict | None:
    """First row with an existing clip: inside the box for a success, outside for a failure."""
    if df.empty or "clip" not in df:
        return None
    succ = df["success"].astype(str).str.lower().isin(("true", "1"))
    region = inside_local(df, box) if want_success else ~inside_local(df, box)
    for _, row in df[(succ == want_success) & region].iterrows():
        if _resolve(row.get("clip")):
            return row.to_dict()
    for _, row in df[succ == want_success].iterrows():
        if _resolve(row.get("clip")):
            return row.to_dict()
    return None


def _clip_caption(clip: Path) -> str | None:
    """Caption from the clip's own transcript (results/transcripts/<hash>.json), if there is one."""
    t = RESULTS / "transcripts" / f"{clip.stem}.json"
    try:
        d = _transcript(str(t), _mtime(t)) if t.exists() else None
    except Exception:
        return None
    if not isinstance(d, dict) or "params" not in d:
        return None
    p, o = d["params"], d.get("outcome") or {}
    mode = "" if o.get("success") else (o.get("failure_mode") or "failure")
    extra = f" · depth {o['depth_mm']:.1f} mm · lateral {o['lateral_mm']:.1f} mm" if "lateral_mm" in o else ""
    return (f"{_badge(mode)} dx={p['dx']:+.3f} m · dy={p['dy']:+.3f} m · yaw={p['yaw']:+.0f}°{extra}"
            f" · {o.get('api_calls', len(d.get('steps', [])))} API calls")


def show_clip(row: dict | None, path_override: str | None, empty_msg: str) -> None:
    clip = _resolve(path_override) if path_override else (_resolve(row.get("clip")) if row else None)
    if clip is None:
        placeholder(empty_msg)
        return
    if clip.suffix.lower() == ".gif":
        st.image(str(clip), width="stretch")
    else:
        st.video(str(clip))
    cap = _clip_caption(clip)
    if not cap and row:
        mode = row.get("failure_mode")
        mode = "" if pd.isna(mode) else str(mode)
        unit = "API calls" if pd.notna(row.get("pose_error_mm")) else "Astra decisions"  # MuJoCo rows log pose error
        cap = (f"{_badge(mode)} dx={row['dx']:+.3f} m · dy={row['dy']:+.3f} m · yaw={row['yaw']:+.0f}° · "
               f"{int(row.get('n_decisions', 0))} {unit}")
    if cap:
        st.markdown(f'<p class="gh-cap">{cap}</p>', unsafe_allow_html=True)


def _headline(feat: dict) -> str | None:
    """Fill the featured headline template from its transcript, so a rerun can't leave stale numbers."""
    t = _resolve(feat.get("failure_transcript"))
    if not feat.get("headline") or t is None:
        return None
    try:
        d = _transcript(str(t), _mtime(t))
        p, o = d["params"], d["outcome"]
        from analysis.coverage import SEARCH_RANGE_MM
        vals = {**p, **o, "search_mm": SEARCH_RANGE_MM,
                "ratio": o["pose_error_mm"] / SEARCH_RANGE_MM}
        return feat["headline"].format(**vals)
    except Exception:
        return None  # a template/transcript mismatch hides the headline rather than showing wrong numbers


def failure_clips(df: pd.DataFrame, featured: str | None) -> list[dict]:
    """Failed rows with an existing clip; the featured clip first."""
    if df.empty or "clip" not in df:
        return []
    succ = df["success"].astype(str).str.lower().isin(("true", "1"))
    rows = [r.to_dict() for _, r in df[~succ].iterrows() if _resolve(r.get("clip"))]
    rows.sort(key=lambda r: not (featured and str(r["clip"]).endswith(Path(featured).name)))
    return rows


def _trim(v, limit=1500):
    """Keep decisions verbatim but drop image payloads (long base64 strings)."""
    if isinstance(v, str) and len(v) > limit:
        return f"<{len(v)} chars omitted>"
    if isinstance(v, dict):
        return {k: _trim(x, limit) for k, x in v.items()}
    if isinstance(v, list):
        return [_trim(x, limit) for x in v]
    return v


def _cell(v) -> str:
    return v if isinstance(v, str) else json.dumps(v, default=str)


def show_policy_transcript(data: dict) -> None:
    """MuJoCo peg-in-hole: one policy-writing exchange, then the API-call log of the run."""
    out = data.get("outcome") or {}
    facts = [f"{k}: {out[k]:.1f}" if isinstance(out.get(k), float) else f"{k}: {out[k]}"
             for k in ("failure_mode", "depth_mm", "lateral_mm", "yaw_err_deg") if out.get(k) not in (None, "")]
    if facts:
        st.markdown("**Outcome** — " + " · ".join(facts))
    ex = data.get("policy_exchange") or {}
    resp, code = ex.get("response") or "", ex.get("code") or ""
    st.markdown(f"**Astra's reply** ({ex.get('model', 'Astra')}, verbatim)")
    st.code(resp or "(empty)", language=None, wrap_lines=True, height=200)
    if code and code.strip() not in resp:
        st.markdown("**policy.py**")
        st.code(code, language="python", height=200)
    steps = data.get("steps") or []
    if steps:
        st.markdown(f"**Last {min(5, len(steps))} of {len(steps)} API calls**")
        rows = [{"i": d.get("i"), "api": d.get("api"), "args": _cell(d.get("args")),
                 "result": _cell(d.get("result")), "force_N": d.get("force_N")} for d in steps[-5:]]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def show_transcript(path) -> None:
    p = _resolve(path)
    if p is None:
        st.caption("No transcript for this trial yet.")
        return
    try:
        data = _transcript(str(p), _mtime(p))
    except Exception as e:
        st.caption(f"Transcript unreadable: {e}")
        return
    if isinstance(data, dict) and "policy_exchange" in data:
        show_policy_transcript(data)
        return
    steps = data if isinstance(data, list) else data.get("decisions", data.get("steps", [data]))
    st.caption(f"Last {min(5, len(steps))} of {len(steps)} decisions, verbatim. Prompt text omitted.")
    for d in steps[-5:]:
        d = _trim(d)
        if not isinstance(d, dict):
            st.code(json.dumps(d, indent=1, default=str), language="json", wrap_lines=True)
            continue
        meta = " · ".join(f"{k}: {d[k]}" for k in ("outcome", "error", "elapsed_s") if d.get(k) not in (None, ""))
        st.markdown(f"**Decision {d.get('decision', d.get('step', '?'))}**" + (f" — {meta}" if meta else ""))
        if isinstance(d.get("output"), str) and d["output"].strip():
            st.code(d["output"], language=None, wrap_lines=True)
        if d.get("action") not in (None, "", []):
            act = d["action"] if isinstance(d["action"], str) else json.dumps(d["action"], indent=1, default=str)
            st.code(act, language="json", wrap_lines=True)


def tile(col, label: str, value: float, n: int, hero: bool = False) -> None:
    none = pd.isna(value) or not n
    v = "not run" if none else f"{value:.0%}"
    style = f' style="color:{ACCENT}"' if hero and not none else ""
    col.markdown(f'<div class="gh-tile{" hero" if hero else ""}"><div class="lbl">{label}</div>'
                 f'<div class="val{" none" if none else ""}"{style}>{v}</div><div class="n">n = {n}</div></div>',
                 unsafe_allow_html=True)


def rerun_backend(source: str) -> str:
    """Which sim the Re-run button uses. Real results default to the MuJoCo sim, never silently the fake one
    (sim.trial falls back to fake when GAPHUNTER_SIM is unset)."""
    if os.environ.get("GAPHUNTER_FAKE_RERUN") == "1":
        return "fake"
    return os.environ.get("GAPHUNTER_SIM") or ("mujoco" if source == "real" else "fake")


def rerun_coverage(backend: str, n: int = 10) -> pd.DataFrame:
    from runner.batch import run_batch
    from runner.sample import deploy_box, sample_box

    os.environ["GAPHUNTER_SIM"] = backend  # read by sim.trial in the worker processes
    params = sample_box(deploy_box(), n, seed=random.randint(10_000, 1_000_000))
    bar = st.progress(0.0, text=f"Running 0/{n} trials on the deployment box ({backend} sim)…")

    def progress(done, total):
        bar.progress(done / total, text=f"Running {done}/{total} trials on the deployment box ({backend} sim)…")

    kw = {"force_fake": True} if backend == "fake" else {}
    if "progress" in inspect.signature(run_batch).parameters:
        df = run_batch(params, n_workers=2, tag="rerun", progress=progress, **kw)
    else:
        parts = []
        for i, p in enumerate(params):
            parts.append(run_batch([p], n_workers=1, tag="rerun", **kw))
            progress(i + 1, n)
        df = pd.concat(parts, ignore_index=True)
    bar.progress(1.0, text=f"Done: {int(df['success'].sum())}/{len(df)} succeeded.")
    return df


# ---------------------------------------------------------------- page
POLICIES_JSON = "results/policies.json"
NUM_COLS = ["n local", "local success", "n deploy", "deploy success", "outside-box success"]


def _short_task(task: str) -> str:
    t = str(task or "")
    if "sphere" in t and "basket" in t:
        return "Ditto sphere-in-basket, Franka"
    return t if len(t) <= 34 else t[:33] + "…"


def _policy_box(pid: str, fallback: dict) -> dict:
    try:
        from runner.policies import POLICIES
        return next((m["local_box"] for m in POLICIES if m["policy"] == pid and m.get("local_box")), fallback)
    except Exception:
        return fallback


def _read_rel(rel) -> pd.DataFrame | None:
    p = _resolve(rel)
    return _read_csv(str(p), _mtime(p)) if p else None


def policy_table_html(table: pd.DataFrame, selected: str | None) -> str:
    head = "".join(f"<th>{html.escape(c)}</th>" for c in
                   ["policy", "family", "task", *NUM_COLS, "status"])
    rows = []
    for _, r in table.iterrows():
        cls = "planned" if r["status"] == "planned" else ("sel" if r["id"] == selected else "")
        mark = "▸ " if r["id"] == selected else ""
        cells = [f"<td>{mark}{html.escape(str(r['policy']))}</td>", f"<td>{html.escape(str(r['family']))}</td>",
                 f"<td>{html.escape(_short_task(r['task']))}</td>"]
        cells += [f'<td class="num">{html.escape(str(r[c]))}</td>' for c in NUM_COLS]
        cells.append(f"<td>{html.escape(str(r['status']))}</td>")
        rows.append(f'<tr class="{cls}">' + "".join(cells) + "</tr>")
    return f'<table class="gh-pt"><tr>{head}</tr>{"".join(rows)}</table>'


lb0, db = default_boxes()
policies = load_policies(POLICIES_JSON, root=str(ROOT))
ptable = policy_table(POLICIES_JSON, root=str(ROOT), local_box=lb0, deploy_box=db) if policies else pd.DataFrame()
# Selectable = full or smoke rows that have at least one CSV on disk; planned rows are shown greyed out only.
selectable = [p for p in policies if str(p.get("status")).lower() in ("full", "smoke")
              and (_resolve(p.get("local_csv")) or _resolve(p.get("deploy_csv")))]

st.title("GapHunter")
st.markdown('<p class="gh-sub">The goal of any robotics firm is to deploy a system with four-nines reliability '
            'as cheaply as possible.</p>'
            '<div class="gh-pull"><b>141 local → 89 hidden.</b> Intrinsic AIC 2026: one policy, scored on our own '
            'benchmark and then on the hidden eval.<br><span>The local scenes randomised the board over a radius '
            'about a third smaller than the real one.</span></div>', unsafe_allow_html=True)

sel = None
if selectable:
    ids = [p["policy"] for p in selectable]
    default = next((i for i, p in enumerate(selectable) if str(p.get("status")).lower() == "full"), 0)
    sel_id = st.radio("Show figure and clips for", ids, index=default, horizontal=True, key="policy",
                      label_visibility="collapsed")
    sel = next(p for p in selectable if p["policy"] == sel_id)
if len(ptable):
    st.markdown(policy_table_html(ptable, sel["policy"] if sel else None), unsafe_allow_html=True)
    st.markdown('<p class="gh-src">Select a row above to show its figure and clips · read live from '
                'results/policies.json, numbers recomputed from each row\'s CSVs · planned rows have no CSV yet '
                'and cannot be selected.</p>', unsafe_allow_html=True)

if sel:
    pid = sel["policy"]
    local_df = _read_rel(sel.get("local_csv"))
    deploy_df = _read_rel(sel.get("deploy_csv"))
    local_df = local_df if local_df is not None else pd.DataFrame(columns=["dx", "dy", "yaw", "success"])
    deploy_df = deploy_df if deploy_df is not None else pd.DataFrame(columns=["dx", "dy", "yaw", "success"])
    source = "real"
    lb = _policy_box(pid, lb0)
    is_primary = str(sel.get("deploy_csv") or "") == "results/deploy.csv"
else:  # no policies.json: the single-policy page as before
    local_df, deploy_df, source = load_data()
    pid, lb, is_primary = "astra-script", lb0, True
if is_primary and "extra" in st.session_state:
    deploy_df = pd.concat([deploy_df, st.session_state["extra"]], ignore_index=True)
rep = coverage_report(local_df, deploy_df, lb, db)

t1, t2, t3 = st.columns([1.4, 1, 1])
tile(t1, "success outside the local box", rep["outside_local_success"], rep["n_outside"], hero=True)
tile(t2, "success inside the benchmark", rep["local_success"], rep["n_local"])
tile(t3, "success over the deployment box", rep["deploy_success"], rep["n_deploy"])

if source == "real":
    hm_path = RESULTS / ("heatmap.png" if is_primary else f"heatmap_{pid}.png")
else:
    hm_path = RESULTS / "heatmap_fake.png"
all_df = pd.concat([local_df, deploy_df], ignore_index=True)
try:
    png = _heatmap_png(all_df, str(hm_path), _mtime(ROOT / "analysis" / "coverage.py"), lb, db) if len(all_df) else None
except Exception as e:
    png = None
    st.caption(f"Heatmap failed: {e}")
if png:
    st.image(png, width="stretch")
    if is_primary:
        st.caption("hole_pose() error is a modelled r³ distortion mirroring the AIC calibration radius, "
                   "not a measured camera effect.")
    else:
        st.caption(f"{pid}: {rep['n_local']} local trials, {rep['n_deploy']} deployment trials. The dashed box is "
                   f"this row's local box: dx {lb['dx'][0]:+.2f}…{lb['dx'][1]:+.2f} m, "
                   f"dy {lb['dy'][0]:+.2f}…{lb['dy'][1]:+.2f} m.")
else:
    placeholder(f"No trials for {pid} yet.")

left, right = st.columns([3, 1], gap="medium")
with left:
    if rep["n_deploy"]:
        st.markdown(f'<div class="gh-report"><b>Gap report.</b> {html.escape(rep["text"])}</div>',
                    unsafe_allow_html=True)
    else:
        modes = local_df["failure_mode"].fillna("").astype(str) if "failure_mode" in local_df else pd.Series([], dtype=str)
        counts = ", ".join(f"{m} ×{c}" for m, c in modes[modes != ""].value_counts().items())
        k = int(round(rep["local_success"] * rep["n_local"])) if rep["n_local"] else 0
        st.markdown(f'<div class="gh-report"><b>Smoke run.</b> {pid} succeeded on {k} of {rep["n_local"]} local '
                    f'trials{" (failures: " + counts + ")" if counts else ""}. There are no deployment trials yet, '
                    f'so there is no gap to map.</div>', unsafe_allow_html=True)
    cov_note = (f'coverage = box {" × ".join(rep["coverage_params"])}, local ∕ deployment '
                f'({rep["coverage_fraction_all_params"]:.1%} without yaw folding) · ' if rep["n_deploy"] else "")
    st.markdown(f'<p class="gh-src">Data: {source} · {cov_note}rates from the uniform pass only.</p>',
                unsafe_allow_html=True)
with right:
    backend = rerun_backend(source)
    if st.button("Re-run coverage", type="secondary", disabled=not is_primary,
                 help=(f"Runs 10 new trials sampled over the deployment box, on the {backend} sim."
                       if is_primary else "Re-run is wired to the MuJoCo row (astra-script) only.")):
        try:
            new = rerun_coverage(backend, 10)
            if backend == "fake" and source == "real":
                # Never mix fake-sim trials into real results.
                st.session_state["fake_rerun"] = new
            else:
                st.session_state["extra"] = pd.concat(
                    [st.session_state.get("extra", pd.DataFrame()), new], ignore_index=True)
            st.rerun()
        except Exception as e:
            st.error(f"Re-run failed: {e}")
    if is_primary and "extra" in st.session_state:
        st.caption(f"Includes {len(st.session_state['extra'])} re-run trials from this session ({backend} sim).")
    if "fake_rerun" in st.session_state:
        fr = st.session_state["fake_rerun"]
        st.caption(f"Fake-sim re-run: {int(fr['success'].sum())}/{len(fr)} succeeded. Not merged into real results.")

feat = _featured() if is_primary else {}
both = pd.concat([local_df, deploy_df], ignore_index=True)
c1, c2, c3 = st.columns(3, gap="medium")
with c1:
    st.subheader("In the benchmark")
    ok_row = pick_clip(both, True, lb) if "clip" in both else None
    n_ok = int(both["success"].astype(str).str.lower().isin(("true", "1")).sum()) if len(both) else 0
    show_clip(ok_row, feat.get("success_clip"),
              f"No success clip recorded for {pid}." if n_ok else f"{pid} has no successful trial to show.")
with c2:
    st.subheader("Outside the benchmark")
    fails = failure_clips(deploy_df if is_primary else both, feat.get("failure_clip"))
    if len(fails) > 1:
        def _label(i):
            return f"{fails[i].get('failure_mode') or 'failure'} {i + 1}"
        pick = st.radio("Failure clip", range(len(fails)), format_func=_label, horizontal=True,
                        label_visibility="collapsed")
        bad_row = fails[pick]
        show_clip(bad_row, None, "")
    else:
        bad_row = fails[0] if fails else (pick_clip(both, False, lb) if "clip" in both else None)
        show_clip(bad_row, None if fails else feat.get("failure_clip"), f"No failure clip recorded for {pid}.")
    if bad_row is None and "transcript" in both:  # no clip: still let the transcript explain a failure
        succ = both["success"].astype(str).str.lower().isin(("true", "1"))
        tr = both[~succ & both["transcript"].notna()]
        bad_row = tr.iloc[0].to_dict() if len(tr) else None
is_featured = bool(feat.get("failure_clip")) and (
    bad_row is None or str(bad_row.get("clip", "")).endswith(Path(feat["failure_clip"]).name))
with c3:
    st.subheader("Why it failed")
    head = _headline(feat) if is_featured else None
    if head:
        st.markdown(f'<div class="gh-head">{html.escape(head)}</div>', unsafe_allow_html=True)
    with st.expander("What Astra was thinking"):
        if feat.get("quote") and is_featured:
            st.markdown(f'<blockquote class="gh-quote">“{html.escape(feat["quote"])}”'
                        f'<br><span>— Astra, in the reply that wrote policy.py</span></blockquote>',
                        unsafe_allow_html=True)
        show_transcript((feat.get("failure_transcript") if is_featured else None)
                        or (bad_row or {}).get("transcript"))

feat = _featured()
ditto_clip = _resolve(feat.get("ditto_clip"))
with st.expander("First attempt: Astra driving the Franka live"):
    d1, d2 = st.columns([1, 2], gap="medium")
    with d1:
        if ditto_clip:
            st.video(str(ditto_clip))
            steps = []
            try:
                tp = _resolve(feat.get("ditto_transcript"))
                steps = _transcript(str(tp), _mtime(tp)) if tp else []
            except Exception:
                pass
            secs = sum((x.get("elapsed_s") or 0) for x in steps if isinstance(x, dict))
            st.markdown(f'<p class="gh-cap">Ditto Bench tapered-block variant (medium), run alongside the gate · '
                        f'nominal placement (dx = dy = yaw = 0), seed 1 · {len(steps)} Astra decisions · '
                        f'{secs:.0f} s of model time</p>',
                        unsafe_allow_html=True)
        else:
            placeholder("Ditto clip not found.")
    with d2:
        st.markdown("Astra first drove a Franka on Ditto Bench one decision at a time, from camera images, and "
                    "failed all 6 gate trials at the nominal placement, inside the local box. Each trial took "
                    "about 3 minutes, too slow to sample a deployment domain, so we switched to a policy Astra "
                    "writes once and that runs in MuJoCo in under 2 seconds per trial.")
        show_transcript(feat.get("ditto_transcript"))

st.markdown(
    '<div class="gh-foot">'
    "1. The goal of any robotics firm is to deploy a system with four-nines reliability as cheaply "
    "as possible.<br>"
    "2. Each step-up in the reliability regime — 90%, 99%, 99.9%, 99.99% — is equally difficult."
    "</div>",
    unsafe_allow_html=True,
)
