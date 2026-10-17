# GapHunter

**Demo:** https://ice-citron.github.io/gaphunter/flow.html

**Video:** https://www.youtube.com/watch?v=3-4TG6zC-Rk

## About what we built

The goal of any robotics firm is to deploy a system with four-nines (99.99%) reliability as cheaply as possible.

Foundation models are closing in on the first part of that. As LLMs like Opus improve and robotic foundation
models mature, I believe in one to two years, teams will be able to zero-shot or lightly fine-tune foundation
models to get policies (for arbitrary tasks) that work 90% or 99% of the time. Yet, this is not enough to deploy.

Runs of nines. Each step up the reliability ladder, 90% to 99% to 99.9% to 99.99%, is as hard as the last.
Capability gets you the first nine. The remaining nines come from finding every case where the policy breaks,
and proving you have found them.

Hence, I believe this is where the future gap in the market will be: not in building stronger base policies,
but in helping others to bridge their policies from 90% to 99.99% reliability.

I built GapHunter for this gap. The user uploads a policy for a defined task, and GapHunter runs coverage-driven
tests against it in simulation (MuJoCo and ManiSkill for now), sampling the full deployment workspace rather than
the range the policy was written for, and returns the policy's operating envelope: where it works, where it
degrades, where it fails, and why, with a transcript for every trial and clips of sample failures. It is the
test that tells you whether a policy is actually four-nines, and whether it is acceptable for the real world,
before a customer finds out.

Today it supports two tasks, peg-in-hole and ball grasping, and evaluates five policies side by side: an
Astra-written policy, an Opus-written policy, Astra driving the arm live, Opus driving the arm live, and
MolmoAct2 (a VLA). Pi-0.5 is configured but not yet run (its checkpoint didn't download in time), and Gemini
Robotics and GR00T are placeholders. In the future, this system will be extended to more generic task
categories, be hardware agnostic, support more simulators, and let users define custom tasks and scenes.

## How to get started

**To look around:** open the [demo](https://ice-citron.github.io/gaphunter/flow.html). It replays the
committed runs in this repository; nothing to install.

**To run it yourself** (Linux, Python 3.12; no API key needed for the peg-in-hole task, because the policies
are already written in `results/policies/`):

```bash
git clone https://github.com/Ice-Citron/gaphunter.git && cd gaphunter
python3.12 -m venv .venv
.venv/bin/pip install numpy==2.5.4 scipy==1.18.1 pandas==3.0.6 matplotlib==3.11.2 \
  streamlit==1.66.0 imageio==2.38.1 imageio-ffmpeg==0.6.0 mujoco==3.16.0
git clone --filter=blob:none --sparse https://github.com/google-deepmind/mujoco_menagerie.git third_party/mujoco_menagerie
git -C third_party/mujoco_menagerie sparse-checkout set universal_robots_ur5e
git -C third_party/mujoco_menagerie checkout 62ab00f

make demo          # rebuild the docs from the committed results and open the app on localhost
```

Re-run the peg-in-hole sweep (about 1 minute):

```bash
export GAPHUNTER_SIM=mujoco
.venv/bin/python -m runner.batch  --box local  --n 30  --tag local  --workers 8
.venv/bin/python -m runner.batch  --box deploy --n 600 --tag deploy --workers 8 --render-failures 4
.venv/bin/python -m runner.refine --tag deploy --per-cell 10
.venv/bin/python -m runner.policies && .venv/bin/python -m analysis.fill_docs
```

**What to use:** a policy plugs in through `run_trial(params, render=False) -> TrialResult` in `sim/trial.py`.
On MuJoCo it is a file `results/policies/<name>.py` defining `run(api)` with the four calls in `sim/api.py`
(`hole_pose`, `move_to`, `step_down`, `done`); select it with `GAPHUNTER_POLICY=<name>` and register it in
`runner/policies.py`. The sphere task (ManiSkill / Ditto Bench) needs
[llms-for-robot-control](https://github.com/llong-cs/llms-for-robot-control) installed beside this repository;
see `sim/README.md`.

## File structure

```text
sim/          Simulator backends behind run_trial: MuJoCo peg-in-hole (mj_sim.py, mj_trial.py, api.py),
              Ditto / ManiSkill (ditto_trial.py, ditto_script/, task_override.py), configs and tools
runner/       Sampling (sample.py), batch runner (batch.py), refinement pass (refine.py),
              policy registry (policies.py), fake sim (fake.py)
analysis/     Coverage report and heatmaps (coverage.py), docs and page builders (fill_docs.py, site.py, flow.py)
app/          Streamlit app (streamlit_app.py)
results/      Trial CSVs, policies.json, written policies (policies/), clips/, transcripts/
docs/         GitHub Pages: demo (flow.html), project page (index.html), README template
Makefile      make demo / make docs
```

## Credits

[MuJoCo](https://mujoco.org) and [MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie) (UR5e);
[llms-for-robot-control](https://github.com/llong-cs/llms-for-robot-control) (MIT), ManiSkill 3 / SAPIEN and
Ditto Bench; MolmoAct2; Astra and Opus via API credits.
