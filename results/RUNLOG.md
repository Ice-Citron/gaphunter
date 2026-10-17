# RUNLOG

Real-sim timing (Phase 1, 5 local trials, 1 worker): mean t_wall = TBD s · workers = TBD
Chosen n: n_local = 30 · n_deploy = TBD  (floor(35 min × workers / t_trial), capped 150, floor 80)

## Fake-sim baseline (runner.fake, not real data)
`python -m runner.batch --box local --n 30 --tag fake_local --fake` → 30/30 (100%)
`python -m runner.batch --box deploy --n 100 --tag fake_deploy --fake --render-failures 4` → 10/100 (10%), miss=74, timeout=16
