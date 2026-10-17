"""GapHunter — one dark page: where the benchmark stopped and the failures start."""

from __future__ import annotations

import html
import inspect
import json
import random
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
RESULTS = ROOT / "results"

from analysis.coverage import coverage_report, default_boxes, heatmap  # noqa: E402

st.set_page_config(page_title="GapHunter", layout="wide", initial_sidebar_state="collapsed")

st.markdown(
    """
<style>
[data-testid="stSidebar"], [data-testid="collapsedControl"] {display: none;}
.block-container {padding-top: 1.6rem; padding-bottom: 1rem; max-width: 1280px;}
h1 {margin-bottom: 0 !important;}
.gh-sub {color: #e6e6e6; font-size: 1.15rem; margin: 0 0 .2rem 0;}
.gh-back {color: #8b8f98; font-size: .9rem; margin-bottom: .6rem;}
.gh-tile {background: #1a1d24; border-radius: 8px; padding: .7rem 1rem;}
.gh-tile .lbl {color: #8b8f98; font-size: .8rem; text-transform: uppercase; letter-spacing: .04em;}
.gh-tile .val {font-size: 2.6rem; font-weight: 700; line-height: 1.1;}
.gh-tile .n {color: #8b8f98; font-size: .8rem;}
.gh-ph {background: #2a2d34; color: #8b8f98; border-radius: 8px; height: 220px;
        display: flex; align-items: center; justify-content: center; text-align: center; padding: 1rem;}
.gh-report {font-size: 1rem; line-height: 1.55;}
.gh-src {color: #8b8f98; font-size: .75rem;}
.gh-foot {color: #8b8f98; font-size: .85rem; border-top: 1px solid #30343c; padding-top: .6rem; margin-top: .8rem;}
video {max-height: 300px;}
</style>
""",
    unsafe_allow_html=True,
)

GREEN, RED, GREY = "#2fb36a", "#d64545", "#8b8f98"


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
def _heatmap_png(df_json: str, path: str) -> bytes | None:
    df = pd.read_json(df_json, orient="split")
    lb, db = default_boxes()
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


def _inside(df: pd.DataFrame, box: dict) -> pd.Series:
    m = pd.Series(True, index=df.index)
    for k in ("dx", "dy", "yaw"):
        m &= df[k].between(*box[k])
    return m


def pick_clip(df: pd.DataFrame, want_success: bool, box: dict) -> dict | None:
    """First row with an existing clip: inside the box for a success, outside for a failure."""
    if df.empty or "clip" not in df:
        return None
    succ = df["success"].astype(str).str.lower().isin(("true", "1"))
    region = _inside(df, box) if want_success else ~_inside(df, box)
    for _, row in df[(succ == want_success) & region].iterrows():
        if _resolve(row.get("clip")):
            return row.to_dict()
    for _, row in df[succ == want_success].iterrows():
        if _resolve(row.get("clip")):
            return row.to_dict()
    return None


def show_clip(row: dict | None, path_override: str | None, empty_msg: str) -> None:
    clip = _resolve(path_override) if path_override else (_resolve(row.get("clip")) if row else None)
    if clip is None:
        placeholder(empty_msg)
        return
    if clip.suffix.lower() == ".gif":
        st.image(str(clip), use_container_width=True)
    else:
        st.video(str(clip))
    if row:
        st.caption(f"dx={row['dx']:+.3f} m · dy={row['dy']:+.3f} m · yaw={row['yaw']:+.0f}° · "
                   f"{row.get('failure_mode') or 'success'} · {int(row.get('n_decisions', 0))} decisions")


def _trim(v, limit=1500):
    """Keep decisions verbatim but drop image payloads (long base64 strings)."""
    if isinstance(v, str) and len(v) > limit:
        return f"<{len(v)} chars omitted>"
    if isinstance(v, dict):
        return {k: _trim(x, limit) for k, x in v.items()}
    if isinstance(v, list):
        return [_trim(x, limit) for x in v]
    return v


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
    steps = data if isinstance(data, list) else data.get("decisions", data.get("steps", [data]))
    for d in steps[-5:]:
        d = _trim(d)
        step = d.get("step", "?") if isinstance(d, dict) else "?"
        st.markdown(f"**Decision {step}**")
        out = d.get("output") if isinstance(d, dict) else None
        if isinstance(out, str):
            st.code(out, language=None, wrap_lines=True)
            rest = {k: v for k, v in d.items() if k not in ("step", "output")}
            if rest:
                st.code(json.dumps(rest, indent=1, default=str), language="json", wrap_lines=True)
        else:
            st.code(json.dumps(d, indent=1, default=str), language="json", wrap_lines=True)


def tile(col, label: str, value: float, n: int, color: str) -> None:
    v = "—" if pd.isna(value) else f"{value:.0%}"
    col.markdown(f'<div class="gh-tile"><div class="lbl">{label}</div>'
                 f'<div class="val" style="color:{color}">{v}</div><div class="n">n = {n}</div></div>',
                 unsafe_allow_html=True)


def rerun_coverage(n: int = 10) -> pd.DataFrame:
    from runner.batch import run_batch
    from runner.sample import deploy_box, sample_box

    params = sample_box(deploy_box(), n, seed=random.randint(10_000, 1_000_000))
    bar = st.progress(0.0, text=f"Running 0/{n} trials on the deployment box…")

    def progress(done, total):
        bar.progress(done / total, text=f"Running {done}/{total} trials on the deployment box…")

    if "progress" in inspect.signature(run_batch).parameters:
        df = run_batch(params, n_workers=4, tag="rerun", progress=progress)
    else:
        parts = []
        for i, p in enumerate(params):
            parts.append(run_batch([p], n_workers=1, tag="rerun"))
            progress(i + 1, n)
        df = pd.concat(parts, ignore_index=True)
    bar.progress(1.0, text=f"Done: {int(df['success'].sum())}/{len(df)} succeeded.")
    return df


# ---------------------------------------------------------------- page
local_df, deploy_df, source = load_data()
if "extra" in st.session_state:
    deploy_df = pd.concat([deploy_df, st.session_state["extra"]], ignore_index=True)
lb, db = default_boxes()
rep = coverage_report(local_df, deploy_df, lb, db)

st.title("GapHunter")
st.markdown('<p class="gh-sub">Find where your benchmark stopped before the hidden eval does.</p>'
            '<p class="gh-back">Intrinsic AIC 2026: our policy scored 141 on the local benchmark and 89 on '
            'the hidden eval. The local scenes randomised the board over a radius about 1/3 smaller '
            'than the real one.</p>', unsafe_allow_html=True)

t1, t2, t3 = st.columns(3)
tile(t1, "local success (in the benchmark)", rep["local_success"], rep["n_local"], GREEN)
tile(t2, "deployment success", rep["deploy_success"], rep["n_deploy"], RED)
tile(t3, "outside the local box", rep["outside_local_success"], rep["n_outside"], RED)

left, right = st.columns([3, 2], gap="medium")
with left:
    hm_path = RESULTS / ("heatmap.png" if source == "real" else "heatmap_fake.png")
    all_df = pd.concat([local_df, deploy_df], ignore_index=True)
    try:
        png = _heatmap_png(all_df.to_json(orient="split"), str(hm_path)) if len(all_df) else None
    except Exception as e:
        png = None
        st.caption(f"Heatmap failed: {e}")
    if png:
        st.image(png, use_container_width=True)
    else:
        placeholder("Heatmap appears once results/local.csv and results/deploy.csv exist.")
with right:
    st.subheader("Gap report")
    st.markdown(f'<div class="gh-report">{html.escape(rep["text"])}</div>', unsafe_allow_html=True)
    st.markdown(f'<p class="gh-src">Data: {source} · coverage = box volume (dx × dy × yaw), '
                f'local ∕ deployment.</p>', unsafe_allow_html=True)
    if st.button("Re-run coverage (10 trials, deployment box)", type="primary"):
        try:
            new = rerun_coverage(10)
            st.session_state["extra"] = pd.concat(
                [st.session_state.get("extra", pd.DataFrame()), new], ignore_index=True)
            st.rerun()
        except Exception as e:
            st.error(f"Re-run failed: {e}")
    if "extra" in st.session_state:
        st.caption(f"Includes {len(st.session_state['extra'])} re-run trials from this session.")

feat = _featured()
c1, c2 = st.columns(2, gap="medium")
with c1:
    st.subheader("In the benchmark")
    ok_row = pick_clip(pd.concat([local_df, deploy_df], ignore_index=True), True, lb)
    show_clip(ok_row, feat.get("success_clip"), "Success clip renders here once Agent 1 records one.")
with c2:
    st.subheader("Outside the benchmark")
    bad_row = pick_clip(deploy_df, False, lb)
    show_clip(bad_row, feat.get("failure_clip"), "Failure clip renders here once Agent 1 records one.")
    with st.expander("What Astra was thinking"):
        show_transcript(feat.get("failure_transcript") or (bad_row or {}).get("transcript"))

st.markdown(
    '<div class="gh-foot">'
    "1. The goal of any robotics firm is to deploy a system with four-nines reliability as cheaply "
    "as possible.<br>"
    "2. Each step-up in the reliability regime — 90%, 99%, 99.9%, 99.99% — is equally difficult."
    "</div>",
    unsafe_allow_html=True,
)
