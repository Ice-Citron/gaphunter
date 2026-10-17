"""Measure which object offsets the Franka TCP can physically reach (top-down, no policy).

Run with the ManiSkill venv from the repo root:
  llms-for-robot-control/envs/agentic-framework-maniskill/bin/python sim/tools/reach_probe.py
For each (dx, dy) it resets, drives the TCP with a P-controller on pd_ee_delta_pose to
(object_x, object_y, Z_TARGET) and reports the final XY error. Error < 1.5 cm = reachable.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LRC = ROOT / "llms-for-robot-control"
for p in (LRC / "ditto-bench/src", LRC / "agentic-framework/src", LRC / "agentic-framework/vendor/inspect-robots/src"):
    sys.path.insert(0, str(p))
os.environ.setdefault("DITTO_FRAMEWORK_ROOT", str(LRC / "agentic-framework"))
os.environ.setdefault("MS_ASSET_DIR", str(LRC / "data/maniskill"))
os.environ["DITTO_TASK_RANDOMIZE"] = "0"

import numpy as np  # noqa: E402
from ditto.integration.worker import SuiteSimulator  # noqa: E402

Z_TARGET = float(os.environ.get("REACH_Z", "0.06"))  # TCP height; sphere top is 0.049
STEPS = 60

os.environ["GAPHUNTER_PARAMS"] = json.dumps({"dx": -0.30, "dy": 0.0, "yaw": 0.0})  # sphere off the grid
sys.path.insert(0, str(ROOT))
from sim.task_override import patch  # noqa: E402
import ditto.envs  # noqa: E402,F401
patch()

sim = SuiteSimulator(source_root=LRC / "third_party/molmoact2", assets_root=LRC / "data/molmoact2-sim-eval-assets",
                     control_mode="pd_ee_delta_pose", shader_pack="minimal")
sim.reset(env_id="DittoOddGeometry-v1", seed=0, difficulty="easy")
env = sim.env
low, high = env.action_space.low.reshape(-1), env.action_space.high.reshape(-1)
print("action space", low, high, file=sys.stderr)

rows = []
for dy in (-0.08, 0.0, 0.10, 0.20):
    for dx in (-0.20, -0.15, -0.10, -0.05, 0.0, 0.05, 0.10, 0.15, 0.20):
        sim.reset(env_id="DittoOddGeometry-v1", seed=0, difficulty="easy")
        target = np.array([-0.40 + dx, 0.23 + dy, Z_TARGET])
        # lift, travel at 0.22 m (clears the 0.08 m basket rim), then descend
        for waypoint, steps in ((np.array([*target[:2], 0.22]), STEPS), (target, STEPS)):
            for _ in range(steps):
                tcp = env.unwrapped.agent.tcp.pose.p[0].cpu().numpy()
                a = np.zeros_like(low)
                a[:3] = np.clip((waypoint - tcp) * 20.0, -1, 1)
                a[-1] = low[-1]  # keep gripper open
                env.step(a[None])
        tcp = env.unwrapped.agent.tcp.pose.p[0].cpu().numpy()
        err = float(np.linalg.norm((target - tcp)[:2]))
        rows.append({"dx": dx, "dy": dy, "tcp": tcp.round(3).tolist(), "xy_err": round(err, 3),
                     "z_err": round(float(target[2] - tcp[2]), 3), "reachable": err < 0.015})
        print(json.dumps(rows[-1]), flush=True)
(ROOT / "results").mkdir(exist_ok=True)
(ROOT / "results" / os.environ.get("REACH_OUT", "reach_probe.json")).write_text(json.dumps(rows, indent=1))
