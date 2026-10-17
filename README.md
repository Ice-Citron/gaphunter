# GapHunter

**Find where your benchmark stopped before the hidden eval does.**

![Success rate of the Astra policy over the deployment domain; the dashed box is the local benchmark](results/heatmap.png)

*MicroAGI Physical AI Hackathon, Carnaby St, London.*

## Problem

In Intrinsic AIC 2026 our policy scored 141 on our local benchmark and 89 on the hidden evaluation.
The local scenes randomised the board over a radius about one third smaller than the real one.
The policy did not regress. The benchmark never tested the placements where it fails.

## What GapHunter does

**Sample → run → map → report.** GapHunter takes the benchmark's parameter box and a wider deployment
box (object offset `dx`, `dy`, yaw), draws Sobol samples from both, runs the policy in simulation on
each sample, and scores every trial with the task's own success flag. It then maps success over the
deployment domain, draws the benchmark's box on top, and writes a gap report: what fraction of the
domain the benchmark covers, and which regions fail outside it. The task is Ditto Bench
`DittoOddGeometry-v1` (pick a sphere, place it in a basket) on a Franka arm in ManiSkill 3. The stock
scene jitters the sphere by only ±1 cm.

## Why Astra as the policy

The policy is Astra driving the arm through `llms-for-robot-control`: camera images and robot state
in, a relative motion target out, a low-level controller executes it. LLM-driven policies are the
ones nobody has a deployment benchmark for yet, so they are where a coverage check matters most.

## Two axioms

1. The goal of any robotics firm is to deploy a system with four-nines reliability as cheaply as possible.
2. Each step-up in the reliability regime — 90%, 99%, 99.9%, 99.99% — is equally difficult.

## Results

| | success | n |
|---|---|---|
| Local benchmark box | **TBD** | TBD |
| Deployment box | **TBD** | TBD |
| Deployment, outside the local box | **TBD** | TBD |

> TBD: gap report paragraph from `analysis.coverage`.

## How to reproduce

```bash
python -m venv .venv && .venv/bin/pip install pandas scipy matplotlib streamlit imageio
# sim setup: see sim/README.md (llms-for-robot-control cloned beside this repo, credentials.env)
GAPHUNTER_SIM=ditto .venv/bin/python -m runner.batch --box local  --n 30  --tag local
GAPHUNTER_SIM=ditto .venv/bin/python -m runner.batch --box deploy --n 100 --tag deploy --render-failures 4
.venv/bin/streamlit run app/streamlit_app.py
```

Add `--fake` to either batch command to run the analytic fake sim instead.

## Limitations

- One task, one policy, one simulator. No real hardware.
- n ≈ 100 deployment trials. Each cell of the heatmap holds a few trials, so cell rates are noisy.
- Coverage is box volume. It does not weight regions by how often deployment visits them.
- Yaw is sampled but has no effect on a sphere (the `easy` task). The `medium` task (a tapered block) makes it matter.
- The deployment `dy` range stops at −0.08 m. Below that the sphere starts inside the basket wall.

## Roadmap

- Adaptive boundary search: spend trials where success changes, not uniformly.
- Astra as scenario proposer: let the model suggest the perturbations most likely to break the policy.
- Integration with intrinsic-core and ReSim open-core.
- Real hardware runs for the regions the simulator flags.

## Credits

[llms-for-robot-control](https://github.com/llong-cs/llms-for-robot-control) (MIT),
ManiSkill 3 / SAPIEN, Ditto Bench and MolmoAct2 assets. Astra via OpenAI credits.

## Team

Shi Hao ([@Ice-Citron](https://github.com/Ice-Citron)), with three Claude Code agents (sim, runner,
analysis/UI).
