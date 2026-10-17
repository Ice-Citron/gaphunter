# RUNLOG

**Ditto gate FAILED (Agent A, ~13:05):** nominal 0/6 (friction 0.10 and 0.5, cap 25) -> fallback to the
MuJoCo peg-in-hole sim (`GAPHUNTER_SIM=mujoco`; params dx/dy/yaw/seed become hole offsets). No real Ditto batch was run.
Superseded Ditto plan: 170–290 s/trial, n_local 20, n_deploy 60, 8 workers, cap 25, box dx [-0.12, 0.12], dy [-0.02, 0.20].
MuJoCo fallback (Agent A, commit e864601): 0.1–1.5 s/trial, in-process, deterministic per (params, seed).
Deploy box back to spec v2: dx, dy ±0.20 m, yaw ±90°. Local box ±0.05 m, ±15°. Chosen n: local 30, deploy 150 (brief's cap).

## Real runs (MuJoCo, GAPHUNTER_SIM=mujoco, 8 workers)
13:06:40 `GAPHUNTER_SIM=mujoco .venv/bin/python -m runner.batch --box local --n 30 --tag local --workers 8`
```
n               30
success rate    100.0% (30/30)
failure modes   none
mean decisions  71.00
total wall time 3.5 s (mean 0.12 s/trial)
```
13:06:42 `GAPHUNTER_SIM=mujoco .venv/bin/python -m runner.batch --box deploy --n 150 --tag deploy --workers 8 --render-failures 4`
```
n               150
success rate    18.0% (27/150)
failure modes   miss=123
mean decisions  202.77
total wall time 51.3 s (mean 0.34 s/trial)
clips           4
```
Only one failure mode (`miss`) appeared; no `timeout` (300-call cap) was hit. The spec's ">= 2 failure modes" is not met; not padded.
Failure clips (rows 0, 1, 3, 4; all `miss`): see the `clip` column of deploy.csv.

## Fake-sim baseline (runner.fake: |dx|<0.12, |dy|<0.12, |yaw|<45, 5% flips; not real data)
`python -m runner.batch --box local --n 30 --tag fake_local --fake` → 30/30 (100%)
`python -m runner.batch --box deploy --n 100 --tag fake_deploy --fake --render-failures 4` → 22/100 (22%), miss=60, timeout=18 (re-run 13:07 on the ±0.20 spec deploy box)

## How to run (real sim)
Run from the project `.venv/bin/python`, NOT the framework venv: only the re-exec path has the
240 s per-trial timeout (`GAPHUNTER_TRIAL_TIMEOUT_S`). Enable the real backend with `GAPHUNTER_SIM=ditto`.
`GAPHUNTER_SIM=ditto .venv/bin/python -m runner.batch --box local --n 5 --tag probe --workers 1`
