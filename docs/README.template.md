# GapHunter

**Find where your benchmark stopped before the hidden eval does.**

![Success-rate heatmap; dashed box = local benchmark](results/heatmap.png)

## Problem

In Intrinsic AIC 2026 our policy scored 141 on our local benchmark and 89 on the hidden evaluation.
The local scenes randomised the board over a radius about one third smaller than the real one.
The policy did not get worse; the benchmark never tested the placements where it fails.

## What GapHunter does

**Sample → run → map → report.** GapHunter draws Sobol samples of the object offset (`dx`, `dy`, yaw)
from the benchmark's box and from a wider deployment box. It runs the policy in simulation on each sample,
scores it with Ditto Bench's own success flag, maps success, and reports where it fails outside the
benchmark. Task: `DittoOddGeometry-v1` (put a sphere in a basket), Franka arm, ManiSkill 3.

## Why Astra as the policy

Astra drives the arm through `llms-for-robot-control`: images and robot state in, a relative motion
target out, executed by a low-level controller. Nobody has a deployment benchmark yet for policies that
LLMs write or drive.

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

Yaw is excluded from coverage because it has no effect on a sphere ({coverage_all} with yaw).

## How to reproduce

```bash
GAPHUNTER_SIM=ditto .venv/bin/python -m runner.batch --box local  --n {rows_local} --tag local
GAPHUNTER_SIM=ditto .venv/bin/python -m runner.batch --box deploy --n {rows_deploy} --tag deploy --render-failures 4
.venv/bin/python -m analysis.fill_docs
.venv/bin/streamlit run app/streamlit_app.py
```

Setup: `sim/README.md`. `--fake` runs the fake sim.

## Limitations

- One task, one policy, simulation only.
- n = {n_deploy}, so heatmap cells are noisy.
- Coverage is box area, not weighted by how often deployment visits a region.
- Deployment box limited to the arm's reach: {deploy_box}.
- Object friction raised from 0.10 to 0.5 in both domains (override documented in `sim/README.md`).

## Roadmap

- Adaptive boundary search.
- Astra as scenario proposer.
- intrinsic-core / ReSim open-core integration.
- Real hardware.

## Credits

[llms-for-robot-control](https://github.com/llong-cs/llms-for-robot-control) (MIT), ManiSkill 3 / SAPIEN,
Ditto Bench and MolmoAct2 assets. Astra via OpenAI credits.

## Team

Shi Hao ([@Ice-Citron](https://github.com/Ice-Citron)), with three Claude Code agents (sim, runner,
analysis/UI). MicroAGI Physical AI Hackathon, Carnaby St, London.
