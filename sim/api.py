"""The four functions a policy may call. A policy is `def run(api): ...` and receives this module.

Units: metres and degrees in the world frame; z is up and the table top is z = 0.
The robot holds a 20 x 20 mm square peg, 80 mm long, pointing straight down. The peg tip is the
controlled point. The hole is a 21 x 21 mm square, 50 mm deep, cut into the top of a 50 mm-high block.
"""
from __future__ import annotations

_SIM = None  # set by the trial runner


def hole_pose():
    """Camera estimate of the hole: returns ((x, y, z_top_surface), yaw_deg).
    Yaw is the rotation of the square hole about z, reported in [-45, 45) because a square repeats every 90 degrees."""
    return _SIM.hole_pose()


def move_to(xyz, yaw_deg):
    """Move the peg tip to xyz (metres) with the peg rotated yaw_deg about z, peg pointing down.
    Joint-space motion; blocks until the arm has settled. Moving into the block is a collision."""
    return _SIM.move_to(xyz, yaw_deg)


def step_down(mm):
    """Lower the peg tip by mm millimetres from the last commanded target (negative values raise it).
    Returns the contact force on the peg in newtons after the motion settles.
    The run is aborted as a collision if the contact force ever exceeds 150 N."""
    return _SIM.step_down(mm)


def done():
    """True if the peg tip is at least 30 mm below the block's top surface (i.e. seated in the hole)."""
    return _SIM.done()
