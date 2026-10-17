# GapHunter

**Find where your benchmark stopped before the hidden eval does.** [Live page](https://ice-citron.github.io/gaphunter/)

![GapHunter app](docs/hero.png)

## Problem

In Intrinsic AIC 2026 our policy scored 141 locally and 89 on the hidden evaluation.
The local scenes randomised the board over a radius a third smaller than the real one.
The benchmark never tested where the policy fails.

## What GapHunter does

**Sample → run → map → report.** GapHunter samples the hole offset (`dx`, `dy`, yaw) from the
benchmark's box and a wider deployment box, runs the policy, and maps where
it fails. Task: MuJoCo UR5e peg-in-hole, 20 mm square peg, 21 mm hole. Success: depth ≥ 30 mm, lateral error < 1 mm.

## Why Astra as the policy

Astra writes the policy once: given a four-function API,
it returns `policy.py`, which runs unchanged on every trial. LLM-written policies have no deployment
benchmarks yet.

## Two axioms

1. The goal of any robotics firm is to deploy a system with four-nines reliability as cheaply as possible.
2. Each step-up in the reliability regime — 90%, 99%, 99.9%, 99.99% — is equally difficult.

## Results

![Success-rate heatmap; dashed box = local benchmark](results/heatmap.png)

*`hole_pose()` error is a modelled r³ distortion mirroring the AIC calibration radius, not a measured camera effect.*

The local benchmark covers 2.1% of the deployment domain by volume (dx × dy × yaw; yaw folded to ±45° by the peg symmetry). The policy succeeds on 90% of local trials (n=30) and 16% of deployment trials (n=600); outside the local box it succeeds on 13% (n=586). Failures concentrate in: dx ∈ [+0.13, +0.20] m (0%, n=101); dy ∈ [-0.20, -0.13] m (0%, n=100); dy ∈ [+0.13, +0.20] m (0%, n=100); dx ∈ [-0.20, -0.13] m (1%, n=101). A benchmark that stopped at the local box would have reported 90% and shipped.

Yaw is folded to ±45° (square-peg symmetry; 1.0% unfolded).

## Policies compared

| policy | family | task | n local | local success | n deploy | deploy success | outside-box success | status |
|---|---|---|---|---|---|---|---|---|
| astra-script | LLM-written policy code | peg-in-hole, UR5e | 30 | 90% | 600 | 16% | 13% | full |
| astra-live | LLM closed-loop control | Ditto Bench task 1 (DittoOddGeometry-v1) easy: pick up the 48 mm sphere and put it in the basket, Franka FR3 + Robotiq 2F-85 | 11 | 0/11 (0%) | 3 | 0/3 (0%) | 0/3 (0%) | smoke |
| opus-script | LLM-written policy code | peg-in-hole, UR5e | 30 | 100% | 600 | 22% | 21% | full |
| opus-live | LLM closed-loop control | Ditto Bench task 1 (DittoOddGeometry-v1) easy: pick up the 48 mm sphere and put it in the basket, Franka FR3 + Robotiq 2F-85 | 5 | 0/5 (0%) | 3 | 0/3 (0%) | 0/3 (0%) | smoke |
| molmoact2 | VLA | Ditto Bench task 1 (DittoOddGeometry-v1) easy: pick up the 48 mm sphere and put it in the basket, Franka FR3 + Robotiq 2F-85 | 5 | 1/5 (20%) | 5 | 1/5 (20%) | 1/5 (20%) | smoke |

Any `run_trial(params) -> TrialResult` plugs in; every policy gets the same map and report.
Today two rows are full, three are smoke runs, and none are planned.

## Add your own policy

| piece | contract |
|---|---|
| entry point | `run_trial(params, render=False) -> TrialResult` in `sim/trial.py` |
| `params` | `dx`, `dy` (m), `yaw` (deg): hole offset from nominal; `seed` (int) |
| `TrialResult` | `params`, `success`, `failure_mode` (`""`/`miss`/`drop`/`timeout`/`collision`/`api_error`), `n_decisions`, `t_wall` (s), `clip`, `transcript`, `pose_error_mm` |
| backend | `GAPHUNTER_SIM` = `fake` (default) / `mujoco` / `ditto` |

On MuJoCo a policy is `results/policies/<name>.py` defining `run(api)` with the four calls in `sim/api.py`:

```python
# results/policies/toy.py
def run(api):
    (x, y, z), yaw = api.hole_pose()      # camera estimate of the hole
    api.move_to((x, y, z + 0.02), yaw)    # hover 2 cm above it
    for _ in range(20):                   # descend in 4 mm steps
        api.step_down(4)                  # returns contact force (N); ignored here
        if api.done():                    # seated >= 30 mm deep
            return
```

Copy the `astra-script` entry in `runner/policies.py` `POLICIES`, set `"policy": "toy"` and drop its `*_csv` keys, then:

```bash
for box in local deploy; do GAPHUNTER_SIM=mujoco GAPHUNTER_POLICY=toy .venv/bin/python -m runner.batch --box $box --n 60 --tag $box --policy toy --seed 50000; done
.venv/bin/python -m runner.policies && .venv/bin/python -m analysis.fill_docs
```

Pick an unused `--seed`: artifacts are named by param hash, so seed 0 overwrites astra-script's. "full" needs ≥20 local and ≥50 deploy trials.

## How to reproduce

Setup (Linux, Python 3.12; no API key needed):

```bash
git clone https://github.com/Ice-Citron/gaphunter.git && cd gaphunter
python3.12 -m venv .venv
.venv/bin/pip install numpy==2.5.4 scipy==1.18.1 pandas==3.0.6 matplotlib==3.11.2 \
  streamlit==1.66.0 imageio==2.38.1 imageio-ffmpeg==0.6.0 mujoco==3.16.0
git clone --filter=blob:none --sparse https://github.com/google-deepmind/mujoco_menagerie.git third_party/mujoco_menagerie
git -C third_party/mujoco_menagerie sparse-checkout set universal_robots_ur5e
git -C third_party/mujoco_menagerie checkout 62ab00f
```

Run (about 1 minute):

```bash
export GAPHUNTER_SIM=mujoco
.venv/bin/python -m runner.batch  --box local  --n 30 --tag local  --workers 8
.venv/bin/python -m runner.batch  --box deploy --n 600 --tag deploy --workers 8 --render-failures 4
.venv/bin/python -m runner.refine --tag deploy --per-cell 10
.venv/bin/python -m analysis.fill_docs
.venv/bin/streamlit run app/streamlit_app.py
```

Shortcut:

```bash
make demo
```

Details: `sim/README.md`.

## Limitations

- One task, one policy, simulation only.
- Coverage is unweighted box volume.

**First attempt:** Astra driving a Franka live on Ditto Bench failed our go/no-go gate (0 of 6 nominal-placement trials).

## Roadmap

Adaptive boundary search; Astra-proposed scenarios; intrinsic-core / ReSim; real hardware.

## Credits

MuJoCo + [Menagerie](https://github.com/google-deepmind/mujoco_menagerie) UR5e; Astra via OpenAI credits;
Ditto attempt: [llms-for-robot-control](https://github.com/llong-cs/llms-for-robot-control) (MIT), ManiSkill 3, Ditto Bench.

## Team

Shi Hao ([@Ice-Citron](https://github.com/Ice-Citron)) with three Claude Code agents. MicroAGI Physical AI
Hackathon, London.
