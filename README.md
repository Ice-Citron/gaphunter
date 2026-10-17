# GapHunter

**Find where your benchmark stopped before the hidden eval does.**

![Success-rate heatmap; dashed box = local benchmark](results/heatmap.png)

## Problem

In Intrinsic AIC 2026 our policy scored 141 on our local benchmark and 89 on the hidden evaluation.
The local scenes randomised the board over a radius a third smaller than the real one.
The policy did not regress; the benchmark never tested where it fails.

## What GapHunter does

**Sample → run → map → report.** GapHunter samples the hole offset (`dx`, `dy`, yaw) from the
benchmark's box and a wider deployment box, runs the policy on each sample in simulation, and maps where
it fails. Task: MuJoCo peg-in-hole on a UR5e, a 20 mm square peg into a 21 mm hole. Success is depth ≥ 30 mm with lateral error < 1 mm.

## Why Astra as the policy

Astra writes the policy once: given a four-function API (`hole_pose`, `move_to`, `step_down`, `done`),
it returns `policy.py`, which runs unchanged on every trial. LLM-written policies have no deployment
benchmarks yet.

## Two axioms

1. The goal of any robotics firm is to deploy a system with four-nines reliability as cheaply as possible.
2. Each step-up in the reliability regime — 90%, 99%, 99.9%, 99.99% — is equally difficult.

## Results

| | success | n |
|---|---|---|
| Local benchmark box | **{local_success}** | {n_local} |
| Deployment box | **{deploy_success}** | {n_deploy} |
| Deployment, outside the local box | **{outside_success}** | {n_outside} |

{gap_paragraph}

Yaw is folded to ±45° because the square peg has 90° symmetry ({coverage_all} without folding).

## How to reproduce

```bash
.venv/bin/python -m runner.batch --box local  --n {rows_local} --tag local
.venv/bin/python -m runner.batch --box deploy --n {rows_deploy} --tag deploy --render-failures 4
.venv/bin/python -m analysis.fill_docs
.venv/bin/streamlit run app/streamlit_app.py
```

Setup: `sim/README.md`.

## Limitations

- One task, one policy, simulation only.
- n = {n_deploy}, so heatmap cells are noisy.
- Coverage is unweighted box volume.
- `hole_pose()` is a modelled camera calibrated on the local region. Its radial-distortion error grows
  as r³ (0.3 mm at 5 cm, 15 mm at 20 cm), a model we chose to mirror AIC.

**First attempt:** Astra driving a Franka step by step on Ditto Bench's sphere-in-basket task failed
our gate (0 of 6), so we switched to this fallback.

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
