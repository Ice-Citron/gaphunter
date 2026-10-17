# RUNLOG

**Ditto gate FAILED (Agent A, ~13:05):** nominal 0/6 (friction 0.10 and 0.5, cap 25) -> fallback to the
MuJoCo peg-in-hole sim (`GAPHUNTER_SIM=mujoco`; params dx/dy/yaw/seed become hole offsets). No real Ditto batch was run.
Superseded Ditto plan: 170–290 s/trial, n_local 20, n_deploy 60, 8 workers, cap 25, box dx [-0.12, 0.12], dy [-0.02, 0.20].
MuJoCo timing, box and chosen n: TBD when Agent A's run_trial works.

## Fake-sim baseline (runner.fake: |dx|<0.12, |dy|<0.12, |yaw|<45, 5% flips; not real data)
`python -m runner.batch --box local --n 30 --tag fake_local --fake` → 30/30 (100%)
`python -m runner.batch --box deploy --n 100 --tag fake_deploy --fake --render-failures 4` → 24/100 (24%), miss=57, timeout=19

## How to run (real sim)
Run from the project `.venv/bin/python`, NOT the framework venv: only the re-exec path has the
240 s per-trial timeout (`GAPHUNTER_TRIAL_TIMEOUT_S`). Enable the real backend with `GAPHUNTER_SIM=ditto`.
`GAPHUNTER_SIM=ditto .venv/bin/python -m runner.batch --box local --n 5 --tag probe --workers 1`
