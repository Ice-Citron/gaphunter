import math


def run(api):
    """Force-monitored insertion with bounded, above-surface alignment retries."""
    calls = 0

    def call(function, *args):
        nonlocal calls
        calls += 1
        return function(*args)

    (cx, cy, top), camera_yaw = call(api.hole_pose)

    if not all(math.isfinite(v) for v in (cx, cy, top, camera_yaw)):
        return

    safe_z = top + 0.060
    hover_z = top + 0.001
    force_limit = 15.0
    target_z = safe_z

    def acceptable_force(force):
        return math.isfinite(force) and abs(force) < force_limit

    def lower(mm):
        nonlocal target_z
        # step_down uses the commanded target, not the achieved position.
        target_z -= mm * 0.001
        return call(api.step_down, mm)

    def retract():
        nonlocal target_z
        raise_mm = (safe_z - target_z) * 1000.0
        call(api.step_down, -raise_mm)
        target_z = safe_z

    def candidates():
        # First correct modest yaw error at the camera's estimated centre.
        for dyaw in (0.0, -2.0, 2.0, -4.0, 4.0):
            yield 0.0, 0.0, dyaw

        # Search translation in the hole's local coordinate system.
        spacing = 0.0006
        for radius in (1, 2, 3):
            offsets = [
                (i, j)
                for i in range(-radius, radius + 1)
                for j in range(-radius, radius + 1)
                if max(abs(i), abs(j)) == radius
            ]
            offsets.sort(key=lambda p: p[0] * p[0] + p[1] * p[1])
            for dyaw in (0.0, -2.0, 2.0):
                for i, j in offsets:
                    yield i * spacing, j * spacing, dyaw

    angle = math.radians(camera_yaw)
    c, s = math.cos(angle), math.sin(angle)

    call(api.move_to, (cx, cy, safe_z), camera_yaw)

    for dx, dy, dyaw in candidates():
        # A complete attempt, including insertion and retraction, uses
        # at most 78 calls. This gate keeps the total below 300.
        if calls > 220:
            return

        x = cx + c * dx - s * dy
        y = cy + s * dx + c * dy
        yaw = (camera_yaw + dyaw + 45.0) % 90.0 - 45.0

        # Change lateral position and yaw only after retracting fully.
        call(api.move_to, (x, y, safe_z), yaw)
        call(api.move_to, (x, y, hover_z), yaw)
        target_z = hover_z

        # Reach the nominal surface, then probe in 0.2 mm increments.
        force = lower(1.0)
        clear = acceptable_force(force)
        if clear:
            for _ in range(5):
                force = lower(0.2)
                if not acceptable_force(force):
                    clear = False
                    break

        if not clear:
            retract()
            continue

        # The tip is commanded 1 mm inside: continue without lateral motion.
        seated = False
        for step in range(62):
            force = lower(0.5)
            commanded_depth_mm = 1.0 + 0.5 * (step + 1)

            if not acceptable_force(force):
                seated = bool(call(api.done))
                break

            if commanded_depth_mm >= 30.0:
                if call(api.done):
                    seated = True
                    break

        if seated:
            return

        retract()
