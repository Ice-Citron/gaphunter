"""Build docs/index.html, the static landing page served by GitHub Pages, from committed files only.

    python -m analysis.site        # also called by analysis.fill_docs

Text comes from the rendered README.md, numbers from results/*.csv via coverage_report, the table from
results/policies.json, clips and the failure sentence from results/featured.json and the clip's transcript.
Assets are copied into docs/assets/, because Pages serves docs/ only.
"""

from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
from pathlib import Path

import pandas as pd

from analysis.coverage import (ACCENT, POLICY_COLUMNS, SEARCH_RANGE_MM, _range, coverage_report, default_boxes,
                               policy_table)

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
ASSETS = DOCS / "assets"
NUM_COLS = POLICY_COLUMNS[3:8]


def _readme() -> str:
    return (ROOT / "README.md").read_text()


def _section(md: str, title: str) -> str:
    m = re.search(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", md, re.S | re.M)
    return m.group(1).strip() if m else ""


def _inline(md: str) -> str:
    """Minimal inline Markdown: **bold**, *italic*, `code`, [text](url)."""
    s = html.escape(md)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\*([^*]+)\*", r"<i>\1</i>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
    return s


def _repo_url() -> str:
    url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT, capture_output=True,
                         text=True).stdout.strip()
    return re.sub(r"\.git$", "", url)


def _copy(rel: str | None) -> str | None:
    if not rel or not (ROOT / rel).is_file():
        return None
    ASSETS.mkdir(parents=True, exist_ok=True)
    dst = ASSETS / Path(rel).name
    shutil.copyfile(ROOT / rel, dst)
    return f"assets/{dst.name}"


def _headline(feat: dict) -> str | None:
    t = ROOT / str(feat.get("failure_transcript") or "")
    if not feat.get("headline") or not t.is_file():
        return None
    d = json.loads(t.read_text())
    o = d["outcome"]
    return feat["headline"].format(**d["params"], **o, search_mm=SEARCH_RANGE_MM,
                                   ratio=o["pose_error_mm"] / SEARCH_RANGE_MM)


def _clip_caption(rel: str | None) -> str:
    t = ROOT / "results/transcripts" / f"{Path(rel or '').stem}.json"
    if not rel or not t.is_file():
        return ""
    d = json.loads(t.read_text())
    p, o = d["params"], d.get("outcome") or {}
    res = "success" if o.get("success") else (o.get("failure_mode") or "failure")
    return (f"dx {p['dx']:+.3f} m · dy {p['dy']:+.3f} m · yaw {p['yaw']:+.0f}° · {res} · "
            f"lateral {o.get('lateral_mm', 0):.1f} mm · {o.get('api_calls', len(d.get('steps', [])))} API calls")


def _short_task(task: str) -> str:
    t = str(task or "")
    return "Ditto sphere-in-basket, Franka" if "sphere" in t and "basket" in t else t


def _views(lb: dict, db: dict, model_note: str, policies_path: str) -> list[dict]:
    """One view per selectable policy row (full or smoke, with a CSV): numbers, gap text and its own figure."""
    from analysis.coverage import heatmap, load_policies
    try:
        from runner.policies import POLICIES
        boxes = {m["policy"]: m["local_box"] for m in POLICIES if m.get("local_box")}
    except Exception:
        boxes = {}
    empty = pd.DataFrame(columns=["dx", "dy", "yaw", "success"])
    views = []
    for pol in load_policies(policies_path, root=str(ROOT)):
        status = str(pol.get("status") or "planned").lower()
        frames = {k: pd.read_csv(ROOT / pol[k]) for k in ("local_csv", "deploy_csv")
                  if pol.get(k) and (ROOT / pol[k]).is_file()}
        if status == "planned" or not frames:
            continue
        pid = pol["policy"]
        ldf, ddf = frames.get("local_csv", empty), frames.get("deploy_csv", empty)
        box = boxes.get(pid, lb)
        r = coverage_report(ldf, ddf, box, db)
        ASSETS.mkdir(parents=True, exist_ok=True)
        img = ASSETS / f"heatmap_{re.sub(r'[^A-Za-z0-9_-]', '_', pid)}.png"
        heatmap(pd.concat([ldf, ddf], ignore_index=True), local_box=box, deploy_box=db, path=str(img), policy=pid)
        pct = lambda v, n: f"{v:.0%}" if n else "not run"  # noqa: E731
        if r["n_deploy"]:
            text = r["text"]
        else:
            k = int(round(r["local_success"] * r["n_local"])) if r["n_local"] else 0
            text = f"Smoke run: {k} of {r['n_local']} local trials succeeded; no deployment trials yet."
        has_err = "pose_error_mm" in ddf and ddf["pose_error_mm"].notna().any()
        views.append({"id": pid, "status": status, "img": f"assets/{img.name}",
                      "eyebrow": f"{pid} · {status} · {r['n_local']} local · {r['n_deploy']} deployment trials",
                      "out": pct(r["outside_local_success"], r["n_outside"]), "nout": f"n = {r['n_outside']}",
                      "loc": pct(r["local_success"], r["n_local"]), "nloc": f"n = {r['n_local']}",
                      "dep": pct(r["deploy_success"], r["n_deploy"]), "ndep": f"n = {r['n_deploy']}",
                      "note": re.sub(r"`", "", model_note) if has_err else "", "text": text})
    return views


def build(policies_path: str = "results/policies.json", out_name: str = "index.html") -> Path:
    md = _readme()
    lb, db = default_boxes()
    ldf, ddf = pd.read_csv(ROOT / "results/local.csv"), pd.read_csv(ROOT / "results/deploy.csv")
    r = coverage_report(ldf, ddf, lb, db)
    feat = json.loads((ROOT / "results/featured.json").read_text())

    pitch = re.search(r"^\*\*(.+?)\*\*", md, re.M).group(1)
    problem = _section(md, "Problem").split("\n")
    nums = re.search(r"scored (\d+) locally and (\d+) on the hidden", " ".join(problem))
    aic_local, aic_hidden = nums.group(1), nums.group(2)
    problem_rest = " ".join(problem[1:])
    axioms = [re.sub(r"^\d+\.\s*", "", line) for line in _section(md, "Two axioms").splitlines() if line.strip()]
    caption = re.search(r"^\*(`hole_pose\(\)`.+?)\*$", md, re.M).group(1)

    views = _views(lb, db, caption, policies_path)
    default_view = next((k for k, v in enumerate(views) if v["status"] == "full"), 0)
    ok_clip, bad_clip = _copy(feat.get("success_clip")), _copy(feat.get("failure_clip"))
    head = _headline(feat) or ""

    table = policy_table(policies_path, root=str(ROOT), local_box=lb, deploy_box=db)
    trs = []
    for _, row in table.iterrows():
        cls = ' class="planned"' if row["status"] == "planned" else ""
        cells = [html.escape(str(row["policy"])), html.escape(str(row["family"])),
                 html.escape(_short_task(row["task"]))]
        cells += [html.escape(str(row[c])) for c in NUM_COLS] + [html.escape(str(row["status"]))]
        trs.append(f"<tr{cls}>" + "".join(f'<td{" class=num" if 3 <= i <= 7 else ""}>{c}</td>'
                                          for i, c in enumerate(cells)) + "</tr>")
    ths = "".join(f"<th>{html.escape(c)}</th>" for c in POLICY_COLUMNS)

    dx, dy, yaw = (_range(db, p) for p in ("dx", "dy", "yaw"))
    gap = r["gap_regions"][0] if r["gap_regions"] else None
    task = next((row["task"] for _, row in table.iterrows() if row["status"] == "full"), "")
    how = [
        ("Sample", f"{r['n_local']} points in the benchmark's box, {r['n_deploy']} Sobol points over the "
                   f"deployment box (dx {dx[0]:+.2f}…{dx[1]:+.2f} m, dy {dy[0]:+.2f}…{dy[1]:+.2f} m, "
                   f"yaw {yaw[0]:+.0f}…{yaw[1]:+.0f}°)."),
        ("Run", f"each point through <code>run_trial(params) → TrialResult</code>: {html.escape(str(task))}."),
        ("Map", "success rate per cell, with the benchmark's box drawn on top."),
        ("Report", f"the benchmark covers {r['coverage_fraction']:.1%} of the domain"
                   + (f"; the worst band is {gap['param']} {gap['range'][0]:+.2f}…{gap['range'][1]:+.2f} at "
                      f"{gap['success']:.0%} (n={gap['n']})." if gap else ".")),
    ]
    repo = _repo_url()

    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GapHunter</title>
<meta name="description" content="{html.escape(pitch)}">
<style>
:root {{ --bg: #08090a; --panel: #101113; --ink: #f7f8f8; --muted: #8a8f98; --faint: #3a3d43;
        --line: #1d1f23; --accent: {ACCENT}; }}
* {{ box-sizing: border-box; }}
html {{ -webkit-text-size-adjust: 100%; }}
body {{ margin: 0; background: var(--bg); color: var(--ink); line-height: 1.5;
       font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }}
a {{ color: var(--ink); text-decoration: underline; text-decoration-color: var(--faint); text-underline-offset: 3px; }}
a:hover {{ text-decoration-color: var(--ink); }}
code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: .9em; color: var(--ink); }}
.wrap {{ max-width: 1120px; margin: 0 auto; padding: 0 24px; }}
section {{ padding: 96px 0; border-top: 1px solid var(--line); }}
section:first-of-type {{ border-top: 0; }}
.eyebrow {{ color: var(--muted); font-size: 13px; letter-spacing: .08em; text-transform: uppercase; margin: 0 0 20px; }}
h1 {{ font-size: clamp(48px, 9vw, 104px); line-height: 1; letter-spacing: -.045em; font-weight: 650; margin: 0 0 24px; }}
h2 {{ font-size: clamp(28px, 4vw, 44px); letter-spacing: -.03em; line-height: 1.1; font-weight: 600; margin: 0 0 32px; }}
.lede {{ font-size: clamp(20px, 2.4vw, 26px); color: var(--muted); max-width: 760px; margin: 0; letter-spacing: -.01em; }}
.cta {{ margin-top: 40px; display: flex; gap: 24px; flex-wrap: wrap; font-size: 15px; }}
.quote {{ font-size: clamp(56px, 10vw, 128px); font-weight: 650; letter-spacing: -.05em; line-height: 1; margin: 0 0 28px; }}
.quote .arrow {{ color: var(--muted); font-weight: 400; }}
.quote small {{ display: block; font-size: 15px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); font-weight: 500; margin-top: 16px; }}
.prose {{ font-size: 19px; color: var(--muted); max-width: 720px; margin: 0; }}
.nums {{ display: grid; grid-template-columns: 1.6fr 1fr 1fr; gap: 32px; align-items: end; }}
.num .v {{ font-size: clamp(40px, 6vw, 64px); font-weight: 600; letter-spacing: -.04em; line-height: 1; }}
.num.hero .v {{ font-size: clamp(88px, 15vw, 184px); color: var(--accent); font-weight: 650; }}
.num .l {{ color: var(--muted); font-size: 15px; margin-top: 12px; }}
.num .n {{ color: var(--faint); font-size: 13px; font-variant-numeric: tabular-nums; }}
.num.hero .v.none {{ color: var(--faint); font-size: clamp(40px, 6vw, 64px); }}
.seg {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 32px; }}
.seg button {{ font: inherit; font-size: 14px; color: var(--muted); background: transparent; border: 1px solid var(--line);
              border-radius: 999px; padding: 6px 14px; cursor: pointer; }}
.seg button:hover {{ color: var(--ink); }}
.seg button[aria-selected="true"] {{ color: var(--ink); background: var(--panel); border-color: var(--faint); }}
figure {{ margin: 0; }}
figure img {{ width: 100%; height: auto; display: block; border-radius: 12px; border: 1px solid var(--line); }}
figcaption {{ color: var(--muted); font-size: 14px; margin-top: 16px; }}
.tbl {{ overflow-x: auto; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; min-width: 720px; }}
th {{ text-align: left; color: var(--muted); font-weight: 500; padding: 10px 8px; border-bottom: 1px solid var(--line); }}
td {{ padding: 12px 8px; border-bottom: 1px solid var(--line); color: var(--ink); }}
td.num {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
tr.planned td {{ color: var(--faint); }}
.clips {{ display: grid; grid-template-columns: 1fr 1fr; gap: 32px; }}
.clip video {{ width: 100%; border-radius: 12px; border: 1px solid var(--line); background: #000; display: block; }}
.clip h3 {{ font-size: 15px; font-weight: 500; color: var(--muted); margin: 0 0 14px; letter-spacing: .02em; }}
.clip p {{ color: var(--faint); font-size: 13px; margin: 12px 0 0; }}
.why {{ font-size: clamp(20px, 2.4vw, 26px); letter-spacing: -.01em; max-width: 900px; margin: 48px 0 0; }}
.how {{ list-style: none; padding: 0; margin: 0; display: grid; gap: 28px; max-width: 900px; }}
.how li {{ display: grid; grid-template-columns: 120px 1fr; gap: 24px; font-size: 19px; color: var(--muted); }}
.how b {{ color: var(--ink); font-weight: 600; }}
footer {{ border-top: 1px solid var(--line); padding: 64px 0 96px; color: var(--muted); }}
footer ol {{ margin: 0 0 40px; padding-left: 20px; font-size: 17px; max-width: 760px; }}
footer li {{ margin-bottom: 10px; }}
@media (max-width: 760px) {{
  section {{ padding: 64px 0; }}
  .nums, .clips {{ grid-template-columns: 1fr; }}
  .how li {{ grid-template-columns: 1fr; gap: 4px; }}
}}
</style>
</head>
<body>
<main class="wrap">
<section>
  <p class="eyebrow">GapHunter</p>
  <h1>{html.escape(pitch)}</h1>
  <p class="lede">{_inline(_section(md, "What GapHunter does").split(chr(10))[0])} {_inline(" ".join(_section(md, "What GapHunter does").split(chr(10))[1:]))}</p>
  <div class="cta"><a href="{repo}">Repository →</a><a href="{repo}#how-to-reproduce">Reproduce →</a></div>
</section>

<section>
  <div class="quote">{aic_local} <span class="arrow">→</span> {aic_hidden}<small>Intrinsic AIC 2026 · local benchmark → hidden eval</small></div>
  <p class="prose">{_inline(problem_rest)}</p>
</section>

<section>
  <div class="seg" role="tablist">{"".join(f'<button data-i="{k}" role="tab">{html.escape(v["id"])}</button>' for k, v in enumerate(views))}</div>
  <p class="eyebrow" id="v-eyebrow"></p>
  <div class="nums">
    <div class="num hero"><div class="v" id="v-out"></div><div class="l">success outside the local box</div><div class="n" id="v-nout"></div></div>
    <div class="num"><div class="v" id="v-loc"></div><div class="l">inside the benchmark</div><div class="n" id="v-nloc"></div></div>
    <div class="num"><div class="v" id="v-dep"></div><div class="l">over the deployment box</div><div class="n" id="v-ndep"></div></div>
  </div>
  <figure style="margin-top:64px">
    <img id="v-img" alt="Success-rate heatmap, success by dy, and success by perception error; dashed box = local benchmark">
    <figcaption><span id="v-note"></span> <span id="v-text"></span></figcaption>
  </figure>
</section>
<script>
const VIEWS = {json.dumps(views)};
function show(k) {{
  const v = VIEWS[k];
  document.querySelectorAll(".seg button").forEach((b, i) => b.setAttribute("aria-selected", i === k));
  for (const [id, key] of [["v-eyebrow","eyebrow"],["v-out","out"],["v-nout","nout"],["v-loc","loc"],["v-nloc","nloc"],
                           ["v-dep","dep"],["v-ndep","ndep"],["v-note","note"],["v-text","text"]])
    document.getElementById(id).textContent = v[key];
  document.getElementById("v-out").classList.toggle("none", v.out === "not run");
  document.getElementById("v-img").src = v.img;
}}
document.querySelectorAll(".seg button").forEach(b => b.addEventListener("click", () => show(+b.dataset.i)));
show({default_view});
</script>

<section>
  <h2>Policies compared</h2>
  <div class="tbl"><table><tr>{ths}</tr>{"".join(trs)}</table></div>
</section>

<section>
  <div class="clips">
    <div class="clip"><h3>In the benchmark</h3>{f'<video src="{ok_clip}" controls muted loop playsinline preload="metadata"></video>' if ok_clip else ""}<p>{html.escape(_clip_caption(feat.get("success_clip")))}</p></div>
    <div class="clip"><h3>Outside the benchmark</h3>{f'<video src="{bad_clip}" controls muted loop playsinline preload="metadata"></video>' if bad_clip else ""}<p>{html.escape(_clip_caption(feat.get("failure_clip")))}</p></div>
  </div>
  <p class="why">{html.escape(head)}</p>
</section>

<section>
  <h2>How it works</h2>
  <ol class="how">{"".join(f"<li><b>{k}</b><span>{v}</span></li>" for k, v in how)}</ol>
</section>
</main>

<footer>
  <div class="wrap">
    <ol>{"".join(f"<li>{_inline(a)}</li>" for a in axioms)}</ol>
    <a href="{repo}">{html.escape(repo.replace("https://", ""))}</a>
  </div>
</footer>
</body>
</html>
"""
    DOCS.mkdir(exist_ok=True)
    (DOCS / ".nojekyll").write_text("")
    out = DOCS / out_name
    out.write_text(page)
    return out


if __name__ == "__main__":
    print(build())
