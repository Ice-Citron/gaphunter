# sim/ — GapHunter wrapper around llms-for-robot-control + Ditto Bench

Owner: Agent 1. Paths below are relative to `llms-for-robot-control/` (cloned beside this
repo at `Project-Sienar/llms-for-robot-control/`, gitignored, not vendored).

## 1. Chosen task

**`DittoOddGeometry-v1`, task id `1`, difficulty `easy`.** "Pick up the blue object and put it in
the basket." The object is a 48 mm sphere (friction 0.10). The basket is a fixed 240x200 mm box with an
80 mm rim.

- Catalog: `ditto-bench/src/ditto/catalog.py:22` (`TaskSpec(1, "DittoOddGeometry-v1", ...)`).
- Env class: `ditto-bench/src/ditto/tasks/geometry_tasks.py:407-408` (`@register_env("DittoOddGeometry-v1")`, `OddGeometryEnv`).
- Success: `geometry_tasks.py:542` `goal_reached = contained & released` (the whole XY footprint is inside
  the basket and the gripper does not touch it). `SUCCESS_HOLD_SECONDS = 0.0`, so success needs one step only.
  The flag comes from `base.py:237` `success=(self._hold_steps >= required) & ~fail`.
- This is the only single pick-and-place task. The others are extraction, insertion, standing, tool use
  and ring removal.
- **Yaw is a null dimension for `easy`** because a sphere is rotation-invariant. Keep it in the sampler: a
  flat yaw slice in the report shows that the analysis works. If yaw must matter, switch to `medium`
  (a tapered block, nominal yaw 45 deg, `geometry_tasks.py:417`). This is a one-word change in `sim/agent.json`.

## 2. The function that runs one episode

The chain is `scripts/eval.py:523 main` -> `build_plan` (`:149`), which writes `<out>/eval-config.json` and builds the job
command at `:345`:
`python -B -P -m ditto.integration.agentic --config <out>/eval-config.json [...]`
-> `scripts/eval_parallel.py run_parallel` launches it as a subprocess
-> `ditto-bench/src/ditto/integration/agentic.py:62 main(argv)` patches the framework (`framework_suite_bindings`, `:26`)
-> `agentic-framework/src/agentic_framework/harness/run.py:762 main(argv)` -> `_main(argv, progress_holder)` (`:200`).

Inside `_main`, each scene runs `robot_eval(task, policy, trial_embodiment, controller=..., seed=scene.init_seed, ...)`
(`run.py:507`, the Inspect Robots rollout loop). `result_row(record, scene, policy, started, control_hz)` (`run.py:112`)
then reads the outcome:

- `row["oracle_success"]` (`run.py:132`) = the last step `terminated and termination_reason == "success"`.
  **This is the bench success flag we use.** It is driven by Ditto's `info["success"]`.
- `row["termination_reason"]`, `row["policy"]["model_calls"]` and the decision counts, `row["wall_time_s"]`, and
  `row["action_audit"][i]["controller"]["task_metrics"]` (per-step Ditto metrics, which include `object_lifted`).
- The row is written to `<out>/evaluation/evals/<scene_id>/result.json` (`run.py:554`). The decisions are written to
  `.../decisions.json` (`policy.py:901`) and to `trajectory.json`. The video goes under `videos/` when
  `record_trajectory` is set.

The simulator runs in a **separate process and venv**. `ditto/integration/embodiment.py:52-80` `SuiteEmbodiment._start`
starts `ditto/integration/worker.py` with `envs/agentic-framework-maniskill/bin/python`. That process holds the
gym env and communicates over stdin/stdout RPC. It inherits `os.environ` (`embodiment.py:56`) and prepends to
`PYTHONPATH` (`:68`). The framework process never imports SAPIEN.

**Plan for `run_trial` (Phase 1):** run in the `envs/agentic-framework` venv and call
`ditto.integration.agentic.main([...])` **in-process**, with one scene per call and a fresh output dir per trial.
This skips `eval_parallel` and does not shell out. Then parse `result.json` and `decisions.json`. The sim worker
is still a child process, which is unavoidable. Expect 10-20 s of SAPIEN start-up per trial.

## 3. Config keys (`examples/agent.json` -> `sim/agent.json`)

| what | key | our value |
|---|---|---|
| model | `llm.model` | `"gpt-6-astra"` (as shipped) |
| temperature | **none**. `ResponsesBackend.prepare_request` (`models/llm/backend.py:616-638`) never sends `temperature` | patched in-process to add `temperature: 0` (see note) |
| reasoning | `llm.augmentations.reasoning.{enabled,effort}` | `effort: "low"` to keep 15 calls under a minute or two |
| max decisions | **none**. Only `execution.max_steps` (control steps) and `execution.k` (steps per decision) exist | `k: 30`, `max_steps: 450` (15 s at 30 Hz) gives at most about 15 decisions, plus a hard cap: we wrap `LLMMotionPolicy.act` (`harness/policy.py:682`) to raise `PolicyStop` after 15 |
| env id / task | `environment.task_ids` + `environment.difficulty` (the Gym id comes from `ditto.catalog`) | `"1"`, `"easy"` |
| seed | `environment.seed` (+`init_start`). The reset seed is `seed + init_start` (`integration/scenes.py:32`) | `params["seed"]`, `init_start: 0`, `trials: 1` |
| layout jitter | `evaluation.task_randomize` -> env `DITTO_TASK_RANDOMIZE` (`agentic.py:81`, `worker.py:95`) | `false`: GapHunter offsets are the only perturbation |
| render / video | `output.record_trajectory` (the worker always uses `render_mode="rgb_array"`, `worker.py:88-95`) | `true` only when `render=True` |
| API key | `llm.env_file` -> `credentials.env` (`OPENAI_API_KEY`, `OPENAI_BASE_URL`) | never committed |

Temperature note: Astra is a reasoning model. If the API rejects `temperature` with reasoning on, we drop the
patch and rely on `effort: low` + `history_length`. We record which one worked here.

## 4. How object placement is randomised

`geometry_tasks.py:416-418` (in `build_task`):
```python
self.object_start = np.asarray((-.40, .23, .001), dtype=np.float32)
self.object_initial_yaw = math.radians(45) if self.difficulty == "medium" else 0.0
self.object_initial_quaternion = quat_euler(0, 0, self.object_initial_yaw)
```
`geometry_tasks.py:487-495` (`OddGeometryEnv.initialize_task`, called from `base.py:135` inside `SuiteTaskEnv._initialize_episode`, `base.py:126`):
```python
def initialize_task(self, env_idx, options):
    positions = np.tile(self.object_start, (len(env_idx), 1))
    quaternions = np.tile(self.object_initial_quaternion, (len(env_idx), 1)).astype(np.float32)
    if self.randomize:
        jitter = self._batched_episode_rng[env_idx].uniform(-1, 1, size=3)
        positions[:, :2] += jitter[:, :2]*.010
        quaternions = np.asarray([quat_euler(0, 0, self.object_initial_yaw+x*math.radians(10))
                                  for x in jitter[:, 2]])
    self.batch_pose(self.odd_object, positions, quaternions, env_idx=env_idx)
```
The stock benchmark therefore jitters the object by only **+/-1 cm and +/-10 deg**, and only with `task_randomize`.
That is the "local benchmark is narrower than deployment" story in its purest form. `reconfiguration_freq=1`
(`base.py:77`) rebuilds the scene on every reset, so `env.reset(seed=s)` already reconfigures.

## Override mechanism (`task_override.py`, `_inject/sitecustomize.py`)

The env lives in the worker process, and its Gym id comes from `ditto.catalog`. A newly registered id
would therefore never be selected by `eval.py` without changes to upstream. Instead:

1. `run_trial` sets `GAPHUNTER_PARAMS='{"dx":..,"dy":..,"yaw":..}'` and `GAPHUNTER_ROOT=<repo>`, and prepends
   `sim/_inject` to `PYTHONPATH`. The worker inherits all of them.
2. In the worker, `sitecustomize.py` installs a meta-path hook. When `ditto.tasks.geometry_tasks` is imported,
   the hook loads `sim/task_override.py` and calls `patch()`. `patch()` wraps `OddGeometryEnv.initialize_task`
   so that it applies `p += (dx, dy, 0)` and `q = yaw_quat * q` after the parent's placement. This runs before
   the progress baseline is taken (`base.py:135` then `:149`). The hook is lazy because `ditto.base` imports
   `sim_eval` (MolmoAct2 source), which the worker puts on `sys.path` only after startup. A test with a stub
   `ditto` package confirmed that the hook fires.
3. For direct Gym use, `task_override.register()` also registers `GapHunter-OddGeometry-v0`, a subclass with
   the same offsets. `TASK_ID` stays `DittoOddGeometry-v1` because `SuiteTaskEnv.__init__` looks it up in the
   catalog (`base.py:65-66`).

Because of the env var, use **one trial per process**: processes for parallelism, never threads.

## Domain limits (changes spec v2's deployment box)

The basket centre is at (-0.40, 0.00) and its outer wall edge is at y = +/-0.116. The object starts at
(-0.40, 0.23) with a radius of 0.024. If `dy < -0.09`, the sphere starts inside the basket wall, and
`dy = -0.23` would put it inside the basket (instant "success"). **Deployment dy = [-0.08, +0.20]**, now in
`runner/sample.py` (A2). dx stays +/-0.20. yaw stays +/-90 and has no effect on `easy`. The robot base position
comes from MolmoAct2's `DroidPutEverythingInBoxEnv.robot_base_p` (not in this checkout until install). Reach at
dx/dy = +/-0.20 is still to be checked on the 5090. The external camera FOV is also unchecked: at large offsets
the object may leave the frame, which is a likely failure mode.

## Headless / Vulkan notes

(fill in on the 5090: vulkaninfo result, ICD path, DISPLAY handling)

## Gate log (12:36-13:00) and outcome: FALLBACK

Pipeline verified end to end. The offset hook fires in the worker: with dx=0.15, the logged sphere pose was x=-0.25 vs default -0.40.
`temperature` is rejected by Astra (HTTP 400), so the patch is off by default (`GAPHUNTER_TEMPERATURE=off`).
Speed config: h=10, k=-1, history 3, effort low. That is about 7-25 s per decision and 140-330 s per episode.

| set | config | nominal (dx=dy=yaw=0) results |
|---|---|---|
| gate 2, 2b | friction 0.10 (native), cap 15 | timeout; drop (lifted, slipped in transfer) |
| medium | tapered block, cap 15 | timeout (grasps missed) |
| seeds 10-12 | friction 0.10, cap 25 | timeout, drop, drop |
| seeds 20-22 | **friction override 0.5** (`task_override.DEFAULT_FRICTION`, `GAPHUNTER_FRICTION`), cap 25 | drop, drop, drop (all reached progress 1.0, then lost the ball in transfer) |

Rule (2 of 3 in either set to stay on Ditto) not met: 0/6. **Fallback to MuJoCo** at 13:00.
Friction override: `task_override.patch()` wraps `geometry_tasks.build_actor` for the `odd_geometry` actor only,
and records `gaphunter_object_friction` in `task_spec`. The default is 0.5. `GAPHUNTER_FRICTION=native` restores 0.10.

Reach probe (`sim/tools/reach_probe.py`, results in `results/reach_probe.json`): top-down TCP at 6 cm, lift-travel-descend P-control.
Reachable: dx in [-0.10, +0.05] for dy in [0, +0.20], dx up to +0.10 for dy >= +0.10, dx down to -0.20 for dy >= +0.10.
Not reachable: dx >= +0.15 at any dy (the gripper cannot descend: IK stalls, matching "no measured motion" in the dx=0.18 run).
At dy=-0.08 the open fingers hit the basket wall. If Ditto is revived, the deploy box is dx [-0.12, +0.12], dy [-0.02, +0.20].

# MuJoCo peg-in-hole fallback (active since 13:00)

`GAPHUNTER_SIM=mujoco`, run from the team `.venv` (`pip install mujoco "imageio[ffmpeg]"`). UR5e model:
`third_party/mujoco_menagerie/universal_robots_ur5e` (sparse clone, gitignored). Rendering: `MUJOCO_GL=egl`.

| file | role |
|---|---|
| `sim/mj_sim.py` | scene (UR5e + 20 mm square peg welded at `attachment_site`; 80x80x50 mm block with a 21 mm square hole at (0.45, 0) + (dx, dy), yaw), DLS IK, joint-servo motion with gravity compensation, the perception model, outcome |
| `sim/api.py` | the four policy-facing functions (`hole_pose`, `move_to`, `step_down`, `done`); their docstrings are the API docs Astra sees |
| `sim/write_policy.py` | one Astra call (Responses API, `gpt-6-astra`, reasoning effort medium) → `results/policies/v1.py` + `v1.exchange.json` (prompt, reply, code) |
| `sim/mj_trial.py` | `run_mj_trial`: loads the cached policy, runs `run(api)`, writes the transcript and an optional clip |

Success (`mj_sim.PegSim.outcome`): tip depth >= 30 mm below the top surface and lateral error < 1 mm.
`failure_mode`: `collision` (contact force > 150 N), `timeout` (> 300 API calls or 60 s wall), `api_error`
(the policy raised), else `miss`. `n_decisions` = policy API calls. Same params + seed give the same result.

**Perception model (the gap mechanism, stated openly):** `hole_pose()` models a camera calibrated on the
local region around (0.45, 0). Radial lens distortion is left uncorrected: estimated offset = d * (1 + 1.6 |d|^2), so the
error is 1.6 r^3. That is 0.2 mm at r = 5 cm, 1.6 mm at 10 cm, 9.3 mm at dx = 0.18, and 12.8 mm at 20 cm. The yaw error is
0.1 yaw^3 (rad) on yaw mod 90°. Seeded noise of 0.1 mm / 0.1° is added on top. The physics tolerates about 2 mm (the walls guide the peg).
The prompt tells Astra only the local placement ranges (+/-5 cm, +/-15°), which is the "benchmark" it designed for.

Astra's v1 policy (`results/policies/v1.py`) aligns to the estimate. It retracts on more than 15 N of contact and
searches a +/-1.8 mm grid plus +/-4° yaw. First distribution check (random, not Sobol): local 30/30, deploy 4/40.
Example failure, dx=0.18: the estimate was 9.3 mm off and the search radius is 1.8 mm, so the trial ended with `miss` after 225 calls.
The UR5e reaches the whole deploy box (dx, dy ±0.20, yaw ±90).
