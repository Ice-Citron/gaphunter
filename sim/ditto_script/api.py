"""The five functions a sphere-in-basket policy may call. A policy is `def run(api): ...` and receives this module.

Units: metres, world frame, z up, table top at z = 0. A Franka arm with a parallel gripper pointing straight down.
The object is a 48 mm sphere on the table; the basket is an open box (inner 240 x 200 mm, rim at z = 0.08 m).
"""
_SIM = None


def object_position():
    """(x, y, z) of the sphere's centre."""
    return _SIM.object_position()


def basket_position():
    """(x, y, z) of the centre of the basket floor."""
    return _SIM.basket_position()


def move_to(xyz):
    """Move the gripper's grasp point (between the fingertips) to xyz, gripper pointing down. Blocks until settled.
    Returns the reached (x, y, z)."""
    return _SIM.move_to(xyz)


def set_gripper(closed):
    """Close (True) or open (False) the gripper. Blocks until it settles."""
    return _SIM.set_gripper(closed)


def done():
    """True once the whole sphere is inside the basket and released."""
    return _SIM.done()
