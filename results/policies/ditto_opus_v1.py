import math

MAX_CALLS = 60
SAFE_Z = 0.17      # carry height: sphere bottom stays well above the 0.08 m rim
APPROACH_DZ = 0.10 # hover height above the sphere centre before descending
SPHERE_R = 0.024


def run(api):
    calls = [0]

    def call(fn, *args):
        if calls[0] >= MAX_CALLS:
            raise RuntimeError("budget")
        calls[0] += 1
        return fn(*args)

    def left():
        return MAX_CALLS - calls[0]

    try:
        basket = call(api.basket_position)
        bx, by, bz = basket
        release_z = bz + SPHERE_R + 0.05  # low drop, well inside the rim

        while left() >= 13:
            ox, oy, oz = call(api.object_position)

            # Already in the basket (e.g. dropped there on a previous attempt)?
            if abs(ox - bx) < 0.10 and abs(oy - by) < 0.08 and oz < 0.08:
                call(api.set_gripper, False)
                if call(api.done):
                    return
                # Shallow lift so the gripper is out of the basket before the retry.
                call(api.move_to, (ox, oy, SAFE_Z))

            # Approach from directly above with the gripper open.
            call(api.set_gripper, False)
            call(api.move_to, (ox, oy, max(oz, SPHERE_R) + APPROACH_DZ))
            grasp_z = max(oz, SPHERE_R)  # close at the sphere's equator
            call(api.move_to, (ox, oy, grasp_z))
            call(api.set_gripper, True)

            # Lift straight up, then verify the sphere came with us.
            call(api.move_to, (ox, oy, SAFE_Z))
            px, py, pz = call(api.object_position)
            if pz < 0.06:
                # Slipped out; open and retry from wherever it is now.
                continue

            # Carry over the basket centre, lower, release.
            call(api.move_to, (bx, by, SAFE_Z))
            call(api.move_to, (bx, by, release_z))
            call(api.set_gripper, False)
            if call(api.done):
                return
            # Back off upward before trying again.
            call(api.move_to, (bx, by, SAFE_Z))

        # Final check with whatever budget remains.
        if left() >= 1:
            call(api.done)
    except RuntimeError:
        return
