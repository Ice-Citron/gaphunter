# RUNLOG

Real-sim timing (Phase 1, 5 local trials, 1 worker): mean t_wall = TBD s · workers = TBD
Chosen n: n_local = 30 · n_deploy = TBD  (floor(35 min × workers / t_trial), capped 150, floor 80)

## Fake-sim baseline (runner.fake: |dx|<0.12, |dy|<0.12, |yaw|<45, 5% flips; not real data)
`python -m runner.batch --box local --n 30 --tag fake_local --fake` → 30/30 (100%)
`python -m runner.batch --box deploy --n 100 --tag fake_deploy --fake --render-failures 4` → 24/100 (24%), miss=57, timeout=19

## How to run (real sim)
Run from the project `.venv/bin/python`, NOT the framework venv: only the re-exec path has the
240 s per-trial timeout (`GAPHUNTER_TRIAL_TIMEOUT_S`). Enable the real backend with `GAPHUNTER_SIM=ditto`.
`GAPHUNTER_SIM=ditto .venv/bin/python -m runner.batch --box local --n 5 --tag probe --workers 1`
