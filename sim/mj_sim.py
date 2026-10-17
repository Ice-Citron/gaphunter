"""MuJoCo peg-in-hole (fallback sim): UR5e from mujoco_menagerie, square peg welded to the flange.

World: table top at z=0. The hole fixture is a 80x80x50 mm block with a 21x21 mm square hole
(0.5 mm clearance per side for the 20x20 mm peg), centred at NOMINAL_HOLE + (dx, dy), rotated by yaw.

Perception model (the deliberate, documented gap): hole_pose() is a camera estimate whose
calibration was fitted on the local region around NOMINAL_HOLE. It leaves radial lens distortion
uncorrected, so the position error grows as K_RADIAL * r**3 with r = distance from the calibration
centre (about 0.2 mm at 5 cm, 12.8 mm at 20 cm), and yaw error grows as K_YAW * yaw**3 on the
square's 90-degree-symmetric yaw. Small seeded noise is added on top.
"""
from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np

os.environ.setdefault("MUJOCO_GL", "egl")
import mujoco  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
UR5E = ROOT / "third_party" / "mujoco_menagerie" / "universal_robots_ur5e"

NOMINAL_HOLE = np.array([0.45, 0.0])
TOP_Z = 0.05             # fixture top surface
HOLE_HALF = 0.0105       # 21 mm hole
PEG_HALF = 0.010         # 20 mm peg
PEG_LEN = 0.08
SUCCESS_DEPTH = 0.030
SUCCESS_LATERAL = 0.001
K_RADIAL = 1.6           # m^-2: error = K_RADIAL * r^3
K_YAW = 0.10             # rad^-2: yaw error = K_YAW * yaw^3
NOISE_POS, NOISE_YAW = 1e-4, math.radians(0.1)
COLLISION_N = 150.0
MAX_API_CALLS = 300


def _fixture_xml(dx, dy, yaw_deg):
    a, o, h = HOLE_HALF, 0.04, TOP_Z / 2
    w = (o - a) / 2
    x, y = NOMINAL_HOLE + (dx, dy)
    walls = [((a + w, 0), (w, o)), ((-a - w, 0), (w, o)), ((0, a + w), (a, w)), ((0, -a - w), (a, w))]
    geoms = "\n".join(
        f'<geom type="box" pos="{cx} {cy} {h}" size="{sx} {sy} {h}" rgba="0.55 0.57 0.6 1" friction="0.3"/>'
        for (cx, cy), (sx, sy) in walls)
    return f'''<body name="fixture" pos="{x} {y} 0" euler="0 0 {math.radians(yaw_deg)}">
      {geoms}
      <site name="hole" pos="0 0 {TOP_Z}" size="0.002"/>
    </body>'''


def build_model(dx=0.0, dy=0.0, yaw_deg=0.0) -> mujoco.MjModel:
    arm = (UR5E / "ur5e.xml").read_text()
    arm = arm.replace('meshdir="assets"', f'meshdir="{UR5E / "assets"}"')
    peg = f'''<body name="peg" pos="0 0.1 0" quat="-1 1 0 0">
                    <geom name="peg" type="box" size="{PEG_HALF} {PEG_HALF} {PEG_LEN / 2}" pos="0 0 {PEG_LEN / 2}"
                          rgba="0.95 0.65 0.15 1" friction="0.3" contype="1" conaffinity="1" group="2" mass="0.05"/>
                    <site name="peg_tip" pos="0 0 {PEG_LEN}" size="0.002"/>
                  </body>
                  <site name="attachment_site"'''
    arm = arm.replace('<site name="attachment_site"', peg, 1)
    # strip the outer <mujoco> wrapper so the arm can be inlined with the scene
    body = arm[arm.index(">", arm.index("<mujoco")) + 1: arm.rindex("</mujoco>")]
    xml = f'''<mujoco model="gaphunter peg-in-hole">
  {body}
  <visual><global offwidth="640" offheight="480"/></visual>
  <worldbody>
    <light pos="0.4 0 1.5" dir="0 0 -1" directional="true"/>
    <geom name="table" type="plane" size="1 1 0.05" rgba="0.35 0.3 0.25 1"/>
    {_fixture_xml(dx, dy, yaw_deg)}
    <camera name="side" pos="{NOMINAL_HOLE[0] + dx + 0.28} {dy - 0.28} 0.30" xyaxes="0.707 0.707 0 -0.35 0.35 0.87"/>
    <camera name="overview" pos="1.25 -0.9 0.9" xyaxes="0.6 0.8 0 -0.35 0.26 0.9"/>
  </worldbody>
</mujoco>'''
    return mujoco.MjModel.from_xml_string(xml)


def _target_rot(yaw):
    """Peg axis pointing down, peg x-axis at world yaw."""
    c, s = math.cos(yaw), math.sin(yaw)
    rz = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    rx = np.diag([1.0, -1.0, -1.0])  # 180 deg about x
    return rz @ rx


class PegSim:
    def __init__(self, params: dict, record_every: int = 0):
        self.params = dict(params)
        self.model = build_model(params["dx"], params["dy"], params["yaw"])
        self.data = mujoco.MjData(self.model)
        self.scratch = mujoco.MjData(self.model)
        self.rng = np.random.default_rng(int(params["seed"]))
        key = self.model.key("home")
        self.data.qpos[:] = key.qpos
        self.data.ctrl[:] = key.ctrl
        mujoco.mj_forward(self.model, self.data)
        self.tip = self.model.site("peg_tip").id
        self.peg_geom = self.model.geom("peg").id
        self.calls, self.log, self.frames = 0, [], []
        self.max_force = 0.0
        self.record_every = record_every
        self.renderer = None
        self._step_count = 0
        self.target_xyz = self.data.site_xpos[self.tip].copy()
        self.target_yaw = 0.0
        self._settle(400)
        # start above the nominal hole, 10 cm over the fixture
        self._goto(np.array([*NOMINAL_HOLE, TOP_Z + 0.10]), 0.0)

    # ---------------------------------------------------------------- ground truth
    def hole_true(self):
        x, y = NOMINAL_HOLE + (self.params["dx"], self.params["dy"])
        return np.array([x, y, TOP_Z]), math.radians(self.params["yaw"])

    def outcome(self) -> dict:
        (hx, hy, _), hyaw = self.hole_true()
        tip = self.data.site_xpos[self.tip]
        depth = TOP_Z - tip[2]
        lateral = math.hypot(tip[0] - hx, tip[1] - hy)
        rot = self.data.site_xmat[self.tip].reshape(3, 3)
        peg_yaw = math.atan2(rot[1, 0], rot[0, 0])
        yaw_err = (math.degrees(peg_yaw - hyaw) + 45) % 90 - 45
        success = depth >= SUCCESS_DEPTH and lateral < SUCCESS_LATERAL
        return {"success": bool(success), "depth_mm": round(depth * 1000, 2),
                "lateral_mm": round(lateral * 1000, 3), "yaw_err_deg": round(yaw_err, 2),
                "max_force_N": round(self.max_force, 1)}

    # ---------------------------------------------------------------- physics helpers
    def _contact_force(self) -> float:
        total = 0.0
        f6 = np.zeros(6)
        for i in range(self.data.ncon):
            c = self.data.contact[i]
            if self.peg_geom in (c.geom1, c.geom2):
                mujoco.mj_contactForce(self.model, self.data, i, f6)
                total += abs(f6[0])
        return total

    def _step(self, n):
        for _ in range(n):
            # gravity + Coriolis compensation, as on the real UR controller; removes ~3 mm servo sag
            self.data.qfrc_applied[:] = self.data.qfrc_bias
            mujoco.mj_step(self.model, self.data)
            self._step_count += 1
            if self.record_every and self._step_count % self.record_every == 0:
                self._capture()
        force = self._contact_force()
        self.max_force = max(self.max_force, force)
        return force

    def _settle(self, n=150):
        return self._step(n)

    def _capture(self):
        if self.renderer is None:
            self.renderer = mujoco.Renderer(self.model, 240, 320)
        self.renderer.update_scene(self.data, camera="side")
        self.frames.append(self.renderer.render().copy())

    def _ik(self, xyz, yaw, iters=200):
        m, d = self.model, self.scratch
        d.qpos[:] = self.data.qpos
        target_r = _target_rot(yaw)
        jacp, jacr = np.zeros((3, m.nv)), np.zeros((3, m.nv))
        for _ in range(iters):
            mujoco.mj_kinematics(m, d)
            mujoco.mj_comPos(m, d)
            pos = d.site_xpos[self.tip]
            rot = d.site_xmat[self.tip].reshape(3, 3)
            err_p = xyz - pos
            err_r = 0.5 * (np.cross(rot[:, 0], target_r[:, 0]) + np.cross(rot[:, 1], target_r[:, 1])
                           + np.cross(rot[:, 2], target_r[:, 2]))
            err = np.concatenate([err_p, err_r])
            if np.linalg.norm(err_p) < 1e-5 and np.linalg.norm(err_r) < 1e-4:
                break
            mujoco.mj_jacSite(m, d, jacp, jacr, self.tip)
            j = np.vstack([jacp, jacr])
            dq = j.T @ np.linalg.solve(j @ j.T + 1e-4 * np.eye(6), err)
            d.qpos[:] += np.clip(dq, -0.2, 0.2)
            lo, hi = m.jnt_range[:, 0], m.jnt_range[:, 1]
            limited = m.jnt_limited.astype(bool)
            d.qpos[limited] = np.clip(d.qpos[limited], lo[limited], hi[limited])
        return d.qpos.copy(), float(np.linalg.norm(err_p))

    def _goto(self, xyz, yaw, ramp_steps=250, settle=150):
        q_goal, residual = self._ik(np.asarray(xyz, float), yaw)
        q_start = self.data.ctrl.copy()
        force = 0.0
        for k in range(1, ramp_steps + 1):
            self.data.ctrl[:] = q_start + (q_goal - q_start) * (k / ramp_steps)
            force = max(force, self._step(1))
        force = max(force, self._settle(settle))
        self.target_xyz, self.target_yaw = np.asarray(xyz, float), yaw
        return force, residual

    # ---------------------------------------------------------------- policy-facing API
    def _count(self, api, args, result, force=None):
        self.calls += 1
        tip = self.data.site_xpos[self.tip]
        self.log.append({"i": self.calls, "api": api, "args": args, "result": result,
                         "tcp": [round(float(v), 4) for v in tip],
                         "force_N": None if force is None else round(float(force), 2)})
        if self.calls > MAX_API_CALLS:
            raise ApiCapReached()
        if self.max_force > COLLISION_N:
            raise CollisionStop()

    def hole_pose(self):
        (x, y, z), yaw = self.hole_true()
        d = np.array([x, y]) - NOMINAL_HOLE
        r = float(np.linalg.norm(d))
        est_xy = NOMINAL_HOLE + d * (1 + K_RADIAL * r * r) + self.rng.normal(0, NOISE_POS, 2)
        y90 = (yaw + math.pi / 4) % (math.pi / 2) - math.pi / 4  # camera sees a square: yaw mod 90
        est_yaw = y90 + K_YAW * y90 ** 3 + self.rng.normal(0, NOISE_YAW)
        result = ((float(est_xy[0]), float(est_xy[1]), float(z)), float(math.degrees(est_yaw)))
        self._count("hole_pose", {}, [list(result[0]), result[1]])
        return result

    def move_to(self, xyz, yaw_deg):
        force, residual = self._goto(np.asarray(xyz, float), math.radians(float(yaw_deg)))
        self._count("move_to", {"xyz": [float(v) for v in xyz], "yaw": float(yaw_deg)},
                    {"ik_residual_mm": round(residual * 1000, 2)}, force)

    def step_down(self, mm):
        mm = float(mm)
        target = self.target_xyz - np.array([0, 0, mm / 1000.0])
        force, _ = self._goto(target, self.target_yaw, ramp_steps=max(20, int(abs(mm) * 20)), settle=100)
        self._count("step_down", {"mm": mm}, None, force)
        return float(force)

    def done(self):
        tip = self.data.site_xpos[self.tip]
        seated = bool(TOP_Z - tip[2] >= SUCCESS_DEPTH)  # proprioceptive depth below the surface
        self._count("done", {}, seated)
        return seated


class ApiCapReached(Exception):
    pass


class CollisionStop(Exception):
    pass
