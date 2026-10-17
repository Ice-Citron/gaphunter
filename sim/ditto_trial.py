"""Real run_trial: one Astra episode on Ditto task 1 (easy) with GapHunter offsets.

Must execute inside llms-for-robot-control's `envs/agentic-framework` venv. When called from any
other interpreter (e.g. A2's batch runner), it re-runs itself there as
`python -m sim.ditto_trial '<params json>' [--render]` and parses the last stdout line.

Inside the venv it builds the plan with scripts/eval.py's own resolver, then calls
ditto.integration.agentic.main(argv) in-process: the same evaluator eval_parallel launches.
That evaluator spawns the ManiSkill worker, which picks up the offsets via sim/_inject.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LRC = Path(os.environ.get("GAPHUNTER_LRC", ROOT / "llms-for-robot-control")).resolve()
AGENT_JSON = ROOT / "sim" / "agent.json"
RESULTS = ROOT / "results"
RUNS = RESULTS / "runs"
DECISION_CAP = int(os.environ.get("GAPHUNTER_DECISION_CAP", "15"))
CAP_REASON = "gaphunter_decision_cap"
CLIP_MAX_SIDE, CLIP_MAX_SECONDS = 320, 10.0


def param_hash(params: dict) -> str:
    canon = {"dx": float(params["dx"]), "dy": float(params["dy"]), "yaw": float(params["yaw"]),
             "seed": int(params["seed"])}  # numpy scalars from pandas are not JSON-serialisable
    return hashlib.sha1(json.dumps(canon, sort_keys=True).encode()).hexdigest()


def framework_python() -> Path:
    return LRC / "envs" / "agentic-framework" / "bin" / "python"


def _in_framework_venv() -> bool:
    return Path(sys.prefix).resolve() == (LRC / "envs" / "agentic-framework").resolve()


# ---------------------------------------------------------------- entry point used by sim.trial

def run_ditto_trial(params: dict, render: bool = False):
    from sim.trial import TrialResult

    if not _in_framework_venv():
        return _run_in_subprocess(params, render)
    return TrialResult(**_run_in_process(params, render))


def _run_in_subprocess(params, render):
    from sim.trial import TrialResult

    t0 = time.time()
    clean = {"dx": float(params["dx"]), "dy": float(params["dy"]), "yaw": float(params["yaw"]),
             "seed": int(params["seed"])}
    cmd = [str(framework_python()), "-B", "-m", "sim.ditto_trial", json.dumps(clean)]
    if render:
        cmd.append("--render")
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    lines = [line for line in proc.stdout.splitlines() if line.startswith("GAPHUNTER_RESULT ")]
    if proc.returncode != 0 or not lines:
        log = RESULTS / "transcripts" / f"{param_hash(params)}.stderr.txt"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(proc.stdout[-20000:] + "\n---- stderr ----\n" + proc.stderr[-20000:])
        return TrialResult(dict(params), False, "api_error", 0, time.time() - t0, None, None)
    return TrialResult(**json.loads(lines[-1].removeprefix("GAPHUNTER_RESULT ")))


# ---------------------------------------------------------------- in-venv implementation

def _install_patches():
    """Decision cap + temperature 0. Idempotent; applied in the evaluator (policy) process."""
    from agentic_framework.harness import policy as policy_module
    from agentic_framework.models.llm import backend as backend_module
    from inspect_robots.errors import PolicyStop

    policy_cls = policy_module.LLMMotionPolicy
    if not getattr(policy_cls.act, "_gaphunter", False):
        original_act = policy_cls.act

        def act(self, observation):
            if self._decision_count >= DECISION_CAP:
                raise PolicyStop(CAP_REASON, f"GapHunter cap of {DECISION_CAP} decisions reached")
            return original_act(self, observation)

        act._gaphunter = True
        policy_cls.act = act

    backend_cls = backend_module.ResponsesBackend
    if os.environ.get("GAPHUNTER_TEMPERATURE", "0") != "off" and not getattr(
            backend_cls.prepare_request, "_gaphunter", False):
        original_prepare = backend_cls.prepare_request

        def prepare_request(self, request):
            body = original_prepare(self, request)
            body["temperature"] = float(os.environ.get("GAPHUNTER_TEMPERATURE", "0"))
            return body

        prepare_request._gaphunter = True
        backend_cls.prepare_request = prepare_request


def _framework_argv(params, out: Path, render: bool) -> list[str]:
    for path in (LRC, LRC / "agentic-framework/src", LRC / "ditto-bench/src",
                 LRC / "agentic-framework/vendor/inspect-robots/src"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    from scripts import eval as ev
    from scripts import workspace as w

    os.environ.update(w.child_environment())
    args, extra = ev.parse_arguments([
        str(AGENT_JSON), "--seed", str(int(params["seed"])), "--output-dir", str(out),
        "--record-trajectory" if render else "--no-record-trajectory",
    ])
    plan = ev.build_plan(args, extra)
    out.mkdir(parents=True, exist_ok=True)
    (out / "eval-config.json").write_text(json.dumps(plan["config"], default=str))
    command = list(plan["command"])
    argv = command[command.index("-m") + 2:]  # drop "<python> -B -P -m ditto.integration.agentic"
    return argv + ["--output-dir", str(out / "evaluation")]


def _read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _failure_mode(row) -> str:
    if row is None:
        return "api_error"
    if row.get("oracle_success"):
        return ""
    if row.get("status") in ("discarded", "error", "failed") or row.get("policy", {}).get("transport_failures"):
        return "api_error"
    lifted = any(
        (a.get("controller") or {}).get("task_metrics", {}).get("object_lifted")
        for a in row.get("action_audit", [])
    )
    if lifted:
        return "drop"
    reason = str(row.get("termination_reason", ""))
    if reason == CAP_REASON or "max_steps" in reason or "budget" in reason or "truncat" in reason:
        return "timeout"
    return "miss"


def _short(text, limit=1500):
    if not isinstance(text, str):
        text = json.dumps(text, default=str)
    return text if len(text) <= limit else text[: limit // 2] + " ... " + text[-limit // 2:]


def _write_transcript(decisions, h: str) -> str | None:
    if not decisions:
        return None
    rows = []
    for d in decisions:
        rows.append({
            "step": d.get("observation_step"),
            "decision": d.get("logical_decision_id"),
            "attempt": d.get("attempt"),
            "outcome": d.get("outcome"),
            "observation": _short(d.get("context_text", "")),
            "output": _short(d.get("response_text", ""), 3000),
            "action": d.get("tool_calls"),
            "error": d.get("error", d.get("validation_error")),
            "elapsed_s": d.get("elapsed_s"),
        })
    path = RESULTS / "transcripts" / f"{h}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=1, default=str))
    return str(path.relative_to(ROOT))


def _write_clip(scene_dir: Path, h: str) -> str | None:
    """Downscale the framework's exported MP4 to <=320 px, <=10 s, every 2nd frame."""
    videos = sorted(scene_dir.parent.parent.rglob("*.mp4"))
    if not videos:
        return None
    import imageio.v2 as imageio
    import numpy as np

    reader = imageio.get_reader(str(videos[0]))
    fps = float(reader.get_meta_data().get("fps", 30.0))
    out_fps = fps / 2
    max_frames = int(CLIP_MAX_SECONDS * out_fps)
    # keep the start and the end: sample uniformly if the episode is long
    frames = [f for i, f in enumerate(reader) if i % 2 == 0]
    reader.close()
    if len(frames) > max_frames:
        idx = np.linspace(0, len(frames) - 1, max_frames).astype(int)
        frames = [frames[i] for i in idx]
    hgt, wid = frames[0].shape[:2]
    step = max(1, int(np.ceil(max(hgt, wid) / CLIP_MAX_SIDE)))
    frames = [f[::step, ::step] for f in frames]
    frames = [f[: f.shape[0] // 2 * 2, : f.shape[1] // 2 * 2] for f in frames]  # even dims for h264
    path = RESULTS / "clips" / f"{h}.mp4"
    path.parent.mkdir(parents=True, exist_ok=True)
    imageio.mimwrite(str(path), frames, fps=out_fps, macro_block_size=1)
    return str(path.relative_to(ROOT))


def _safe_clip(scene_dir: Path, h: str) -> str | None:
    try:
        return _write_clip(scene_dir, h)
    except Exception as exc:  # a missing clip must not fail the trial
        print(f"[gaphunter] clip export failed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return None


def _run_in_process(params: dict, render: bool) -> dict:
    t0 = time.time()
    h = param_hash(params)
    out = RUNS / f"{h}-{int(t0)}"
    if out.exists():
        shutil.rmtree(out)
    os.environ["GAPHUNTER_PARAMS"] = json.dumps({k: float(params[k]) for k in ("dx", "dy", "yaw")})
    os.environ["GAPHUNTER_ROOT"] = str(ROOT)
    argv = _framework_argv(params, out, render)
    inject = str(ROOT / "sim" / "_inject")
    os.environ["PYTHONPATH"] = os.pathsep.join(filter(None, (inject, os.environ.get("PYTHONPATH"))))
    _install_patches()

    from ditto.integration import agentic

    try:
        agentic.main(argv)
    except Exception as exc:  # the row below decides; keep the trace for debugging
        print(f"[gaphunter] evaluator raised {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)

    results = sorted((out / "evaluation" / "evals").glob("*/result.json"))
    row = _read_json(results[0]) if results else None
    scene_dir = results[0].parent if results else out
    decisions = _read_json(scene_dir / "decisions.json") or []
    n_decisions = len({d.get("logical_decision_id") for d in decisions if d.get("attempt") == 1})
    return {
        "params": dict(params),
        "success": bool(row and row.get("oracle_success")),
        "failure_mode": _failure_mode(row),
        "n_decisions": n_decisions,
        "t_wall": time.time() - t0,
        "clip": _safe_clip(scene_dir, h) if render else None,
        "transcript": _write_transcript(decisions, h),
    }


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    params = json.loads(sys.argv[1])
    result = _run_in_process(params, render="--render" in sys.argv[2:])
    print("GAPHUNTER_RESULT " + json.dumps(result), flush=True)
