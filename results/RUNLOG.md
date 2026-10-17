# RUNLOG

Real-sim timing (measured by Agent A, 13:00): 170–290 s per trial, API-bound (not GPU); 8 parallel trials run fine.
Plan: n_local = 20 · n_deploy = 60 · workers = 8 · decision cap 25 (`GAPHUNTER_DECISION_CAP=25`) · 4 failure clips.
The floor-80 rule is dropped: 60 deploy trials at ~290 s on 8 workers take ~8 waves ≈ 38 min.

## Fake-sim baseline (runner.fake: |dx|<0.12, |dy|<0.12, |yaw|<45, 5% flips; not real data)
`python -m runner.batch --box local --n 30 --tag fake_local --fake` → 30/30 (100%)
`python -m runner.batch --box deploy --n 100 --tag fake_deploy --fake --render-failures 4` → 24/100 (24%), miss=57, timeout=19

## How to run (real sim)
Run from the project `.venv/bin/python`, NOT the framework venv: only the re-exec path has the
240 s per-trial timeout (`GAPHUNTER_TRIAL_TIMEOUT_S`). Enable the real backend with `GAPHUNTER_SIM=ditto`.
`GAPHUNTER_SIM=ditto .venv/bin/python -m runner.batch --box local --n 5 --tag probe --workers 1`
