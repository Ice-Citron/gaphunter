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
