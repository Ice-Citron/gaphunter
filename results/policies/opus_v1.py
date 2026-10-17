import math

MAX_CALLS = 300


def run(api):
    calls = [0]

    def call(fn, *args):
        calls[0] += 1
        return fn(*args)

    def left():
        return MAX_CALLS - calls[0]

    # 1. Average several camera readings. Yaw uses a circular mean on 4*yaw (square symmetry).
    n_meas = 5
    sx = sy = sz = 0.0
    sc = ss = 0.0
    for _ in range(n_meas):
        (x, y, z), yaw = call(api.hole_pose)
        sx += x
        sy += y
        sz += z
        sc += math.cos(math.radians(4.0 * yaw))
        ss += math.sin(math.radians(4.0 * yaw))
    hx, hy, hz = sx / n_meas, sy / n_meas, sz / n_meas
    hyaw = math.degrees(math.atan2(ss, sc)) / 4.0

    HOVER = 0.0015      # m above top surface for each probe
    PROBE = 2.0         # mm step: ends 0.5 mm below the surface
    CONTACT_N = 15.0    # force meaning "landed on the surface / edge"
    JAM_N = 60.0        # force meaning "jammed while inserting"
    TARGET_DEPTH = 33.0 # mm below the top surface
    INSERT_STEP = 4.0   # mm per insertion step

    # 2. Search candidates: xy spiral (0.4 mm grid) sorted by radius, then small yaw offsets.
    pitch = 0.0004
    pts = []
    n = 8
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            r = math.hypot(i, j) * pitch
            if r <= n * pitch + 1e-9:
                pts.append((r, i * pitch, j * pitch))
    pts.sort(key=lambda p: (round(p[0], 6), math.atan2(p[2], p[1])))
    cands = [(dx, dy, 0.0) for _, dx, dy in pts]
    for dyaw in (1.5, -1.5, 3.0, -3.0):
        for r, dx, dy in pts:
            if r <= 0.0008 + 1e-9:
                cands.append((dx, dy, dyaw))

    def try_insert(px, py, pyaw):
        """Returns True on success. Leaves the peg at the hover height on failure."""
        call(api.move_to, (px, py, hz + HOVER), pyaw)
        f = call(api.step_down, PROBE)
        if f > CONTACT_N:
            call(api.step_down, -PROBE)  # lift off before moving sideways
            return False
        depth = PROBE - HOVER * 1000.0   # mm below the top surface
        while depth < TARGET_DEPTH:
            if left() < 3:
                return bool(call(api.done)) if left() > 0 else False
            step = min(INSERT_STEP, TARGET_DEPTH - depth)
            f = call(api.step_down, step)
            depth += step
            if f > JAM_N:
                # Jammed: back off, then pull completely out and give up on this candidate.
                call(api.step_down, -(depth + HOVER * 1000.0))
                return False
        if call(api.done):
            return True
        # Not reported seated: push slightly further once.
        if left() >= 2:
            f = call(api.step_down, 2.0)
            if f <= JAM_N and call(api.done):
                return True
        return False

    for dx, dy, dyaw in cands:
        # need: move + probe + retract, or move + probe + ~9 insertion steps + done
        if left() < 14:
            break
        if try_insert(hx + dx, hy + dy, hyaw + dyaw):
            return
    return
