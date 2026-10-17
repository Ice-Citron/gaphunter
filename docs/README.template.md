# GapHunter

**Find where your benchmark stopped before the hidden eval does.**

![Success rate of the Astra policy over the deployment domain. The dashed box is the local benchmark.](results/heatmap.png)

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

Astra drives the arm through `llms-for-robot-control`: camera images and robot state go in, a relative
motion target comes out, and a low-level controller executes it. Policies that LLMs write or drive are
the ones nobody has a deployment benchmark for yet.

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

Coverage uses `dx` × `dy` only; yaw is excluded because it has no effect on a sphere ({coverage_all} with yaw).

## How to reproduce

```bash
GAPHUNTER_SIM=ditto .venv/bin/python -m runner.batch --box local  --n 30  --tag local
GAPHUNTER_SIM=ditto .venv/bin/python -m runner.batch --box deploy --n 100 --tag deploy --render-failures 4
.venv/bin/streamlit run app/streamlit_app.py
```

Sim setup: `sim/README.md`. `--fake` uses the analytic fake sim.

## Limitations

- One task, one policy.
- n ≈ 100, so heatmap cells are noisy.
- Coverage is box area, not weighted by how often deployment visits a region.
- Simulation only.

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
