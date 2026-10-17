"""Run a script policy (results/policies/<name>.py, `run(api)`) on Ditto task 1 easy, with GapHunter offsets.

ManiSkill venv:  llms-for-robot-control/envs/agentic-framework-maniskill/bin/python -m sim.ditto_script.run <policy> <box> <n> <seed>
Appends rows to results/ditto_<policy>-script_<box>.csv (B's 12 columns) and writes an mp4 per trial.
"""
import json, os, sys, time, hashlib, importlib.util
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
LRC = ROOT / "llms-for-robot-control"
for p in (LRC / "ditto-bench/src", LRC / "agentic-framework/src", LRC / "agentic-framework/vendor/inspect-robots/src", ROOT):
    sys.path.insert(0, str(p))
os.environ.setdefault("DITTO_FRAMEWORK_ROOT", str(LRC / "agentic-framework"))
os.environ.setdefault("MS_ASSET_DIR", str(LRC / "data/maniskill"))
os.environ["DITTO_TASK_RANDOMIZE"] = "0"
os.environ.setdefault("GAPHUNTER_FRICTION", "native")
import csv
import numpy as np, imageio.v2 as imageio
import sim.task_override as override
import ditto.envs  # noqa: F401
override.patch()
from ditto.integration.worker import SuiteSimulator
from sim.ditto_script import api
from runner.sample import sample_box

BOXES = {"local": {"dx": (-0.05, 0.05), "dy": (-0.02, 0.05), "yaw": (-15.0, 15.0)},
         "deploy": {"dx": (-0.12, 0.12), "dy": (-0.02, 0.20), "yaw": (-90.0, 90.0)}}
MAX_CALLS = 60


class Cap(Exception):
    pass


class DittoScriptSim:
    def __init__(self, sim, record):
        self.sim, self.env, self.calls, self.frames, self.record = sim, sim.env, 0, [], record
        self.low = self.env.action_space.low.reshape(-1); self.high = self.env.action_space.high.reshape(-1)
        self.grip = self.low[-1]; self.steps = 0

    def _tick(self, a):
        self.env.step(a[None]); self.steps += 1
        if self.record and self.steps % 3 == 0:
            self.frames.append(np.asarray(self.env.render()[0].cpu() if hasattr(self.env.render(), "cpu") else self.env.render())[..., :3])

    def _count(self):
        self.calls += 1
        if self.calls > MAX_CALLS:
            raise Cap()

    def tcp(self):
        return self.env.unwrapped.agent.tcp.pose.p[0].cpu().numpy()

    def object_position(self):
        self._count(); return tuple(float(v) for v in self.env.unwrapped.odd_object.pose.p[0].cpu().numpy())

    def basket_position(self):
        self._count(); u = self.env.unwrapped
        return (float(u.basket_origin[0]), float(u.basket_origin[1]), float(u.basket_floor_z))

    def move_to(self, xyz, steps=60):
        self._count(); target = np.asarray(xyz, float)
        for _ in range(steps):
            a = np.zeros_like(self.low); a[:3] = np.clip((target - self.tcp()) * 20.0, -1, 1); a[-1] = self.grip
            self._tick(a)
        return tuple(float(v) for v in self.tcp())

    def set_gripper(self, closed):
        self._count(); self.grip = self.high[-1] if closed else self.low[-1]
        for _ in range(20):
            a = np.zeros_like(self.low); a[-1] = self.grip; self._tick(a)

    def done(self):
        self._count()
        a = np.zeros_like(self.low); a[-1] = self.grip; self._tick(a)
        return bool(self.env.unwrapped.evaluate()["success"][0])


def main():
    policy, box, n, seed = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    spec = importlib.util.spec_from_file_location("pol", ROOT / "results/policies" / f"{policy}.py")
    pol = importlib.util.module_from_spec(spec); spec.loader.exec_module(pol)
    sim = SuiteSimulator(source_root=LRC / "third_party/molmoact2", assets_root=LRC / "data/molmoact2-sim-eval-assets",
                         control_mode="pd_ee_delta_pose", shader_pack="minimal")
    cols = ["dx", "dy", "yaw", "seed", "success", "failure_mode", "n_decisions", "t_wall", "clip", "transcript",
            "pose_error_mm", "pass"]
    name = policy.replace("_v1", "").replace("ditto_", "")  # ditto_astra_v1 -> astra
    out = ROOT / "results" / f"ditto_{name}-script_{box}.csv"
    for p in sample_box(BOXES[box], n, seed=seed):
        t0 = time.time()
        override.OVERRIDE = {k: p[k] for k in ("dx", "dy", "yaw")}
        sim.reset(env_id="DittoOddGeometry-v1", seed=int(p["seed"]), difficulty="easy")
        s = DittoScriptSim(sim, record=True); api._SIM = s; mode = ""
        try:
            pol.run(api)
        except Cap:
            mode = "timeout"
        except Exception as e:  # noqa: BLE001
            mode = "api_error"; print("policy error", repr(e), flush=True)
        ok = bool(sim.env.unwrapped.evaluate()["success"][0]) and mode == ""
        if not ok and not mode:
            mode = "drop" if bool(sim.env.unwrapped._ever_lifted[0]) else "miss"
        h = hashlib.sha1(json.dumps({k: float(p[k]) if k != "seed" else int(p[k]) for k in ("dx", "dy", "yaw", "seed")}, sort_keys=True).encode()).hexdigest()
        clip = ROOT / "results/clips" / f"ditto-{name}-script-{h}.mp4"
        if s.frames:
            fr = s.frames[:: max(1, len(s.frames) // 150)]
            imageio.mimwrite(str(clip), [f[::2, ::2] for f in fr], fps=15, macro_block_size=1)
        row = {"dx": p["dx"], "dy": p["dy"], "yaw": p["yaw"], "seed": p["seed"], "success": ok, "failure_mode": mode,
               "n_decisions": s.calls, "t_wall": time.time() - t0, "clip": str(clip.relative_to(ROOT)) if s.frames else None,
               "transcript": None, "pose_error_mm": None, "pass": 1}
        new = not out.exists()
        with out.open("a", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            if new:
                w.writeheader()
            w.writerow({k: ("" if row[k] is None else row[k]) for k in cols})
        print(box, row, flush=True)


if __name__ == "__main__":
    main()
