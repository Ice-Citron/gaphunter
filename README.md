# GapHunter

**Find where your benchmark stopped before the hidden eval does.**

![Success-rate heatmap; dashed box = local benchmark](results/heatmap.png)

*`hole_pose()` error is a modelled r³ distortion (0.2 mm at 5 cm, 12.8 mm at 20 cm, plus noise)
mirroring the AIC calibration radius, not a measured camera effect.*

## Problem

In Intrinsic AIC 2026 our policy scored 141 locally and 89 on the hidden evaluation.
The local scenes randomised the board over a radius a third smaller than the real one.
The benchmark never tested where the policy fails.

## What GapHunter does

**Sample → run → map → report.** GapHunter samples the hole offset (`dx`, `dy`, yaw) from the
benchmark's box and a wider deployment box, runs the policy on each sample, and maps where
it fails. Task: MuJoCo UR5e peg-in-hole, 20 mm square peg, 21 mm hole. Success is depth ≥ 30 mm with lateral error < 1 mm.

## Why Astra as the policy

Astra writes the policy once: given a four-function API (`hole_pose`, `move_to`, `step_down`, `done`),
it returns `policy.py`, which runs unchanged on every trial. LLM-written policies have no deployment
benchmarks yet.

## Two axioms

1. The goal of any robotics firm is to deploy a system with four-nines reliability as cheaply as possible.
2. Each step-up in the reliability regime — 90%, 99%, 99.9%, 99.99% — is equally difficult.

## Results

The local benchmark covers 2.1% of the deployment domain by volume (dx × dy × yaw; yaw folded to ±45° by the peg symmetry). The policy succeeds on 90% of local trials (n=30) and 16% of deployment trials (n=600); outside the local box it succeeds on 13% (n=586). Failures concentrate in: dx ∈ [+0.13, +0.20] m (0%, n=101); dy ∈ [-0.20, -0.13] m (0%, n=100); dy ∈ [+0.13, +0.20] m (0%, n=100); dx ∈ [-0.20, -0.13] m (1%, n=101). A benchmark that stopped at the local box would have reported 90% and shipped.

Yaw is folded to ±45° by the square peg's symmetry (1.0% unfolded).

## Policies compared

| policy | family | task | n local | local success | n deploy | deploy success | outside-box success | status |
|---|---|---|---|---|---|---|---|---|
| ? | LLM-written policy code | peg-in-hole, UR5e | 30 | 90% | 600 | 16% | 13% | full |
| ? | LLM closed-loop control | sphere-in-basket, Franka FR3 (Ditto OddGeometry) | planned | planned | planned | planned | planned | planned |
| ? | VLA | nan | planned | planned | planned | planned | planned | planned |
| ? | VLA | nan | planned | planned | planned | planned | planned | planned |
| ? | VLA | nan | planned | planned | planned | planned | planned | planned |
| ? | VLA | nan | planned | planned | planned | planned | planned | planned |

The harness takes any `run_trial(params) -> TrialResult`, so every policy gets the same sampling, map and report.
Today one row is full, none are smoke runs, and the rest are planned.

## How to reproduce

Setup (Linux, Python 3.12; no API key needed: Astra's policy is cached in `results/policies/v1.py`):

```bash
git clone https://github.com/Ice-Citron/gaphunter.git && cd gaphunter
python3.12 -m venv .venv
.venv/bin/pip install numpy==2.5.4 scipy==1.18.1 pandas==3.0.6 matplotlib==3.11.2 \
  streamlit==1.66.0 imageio==2.38.1 imageio-ffmpeg==0.6.0 mujoco==3.16.0
git clone --filter=blob:none --sparse https://github.com/google-deepmind/mujoco_menagerie.git third_party/mujoco_menagerie
git -C third_party/mujoco_menagerie sparse-checkout set universal_robots_ur5e
git -C third_party/mujoco_menagerie checkout 62ab00f
```

Run (about 1 minute; CSVs match the committed ones except `t_wall`):

```bash
export GAPHUNTER_SIM=mujoco
.venv/bin/python -m runner.batch  --box local  --n 30 --tag local  --workers 8
.venv/bin/python -m runner.batch  --box deploy --n 600 --tag deploy --workers 8 --render-failures 4
.venv/bin/python -m runner.refine --tag deploy --per-cell 10
.venv/bin/python -m analysis.fill_docs
.venv/bin/streamlit run app/streamlit_app.py
```

Details: `sim/README.md`.

## Limitations

- One task, one policy, simulation only.
- Coverage is unweighted box volume.
- The perception error is modelled (see the heatmap caption).

**First attempt:** Astra driving a Franka on Ditto Bench's sphere-in-basket task failed our go/no-go gate: 0 of 6 nominal-placement trials succeeded.

## Roadmap

- Adaptive boundary search.
- Astra as scenario proposer.
- intrinsic-core / ReSim open-core integration.
- Real hardware.

## Credits

MuJoCo; Astra (`gpt-6-astra`) via OpenAI credits. Ditto attempt:
[llms-for-robot-control](https://github.com/llong-cs/llms-for-robot-control) (MIT), ManiSkill 3, Ditto Bench,
MolmoAct2 assets.

## Team

Shi Hao ([@Ice-Citron](https://github.com/Ice-Citron)) with three Claude Code agents. MicroAGI Physical AI
Hackathon, London.
