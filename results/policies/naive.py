def run(api):
    (x, y, z), yaw = api.hole_pose()
    api.move_to((x, y, z + 0.02), yaw)
    for _ in range(12):
        f = api.step_down(4)
        if api.done():
            return
        if f > 60:
            return
