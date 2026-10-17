import math


def run(api):
    remaining = 60

    def call(fn, *args):
        nonlocal remaining
        if remaining <= 0:
            raise RuntimeError("API call budget exhausted")
        remaining -= 1
        return fn(*args)

    basket = call(api.basket_position)
    travel_z = max(0.18, basket[2] + 0.18)
    reached = None

    # A slightly below-equator pinch helps support a slippery sphere.
    # Retry progressively lower, without commanding the grasp point
    # below the table.
    for depth in (0.004, 0.008, 0.010):
        if remaining < 18:
            break
        if call(api.done):
            return

        call(api.set_gripper, False)
        sphere = call(api.object_position)

        reached = call(
            api.move_to,
            (sphere[0], sphere[1], max(travel_z, sphere[2] + 0.10)),
        )
        grasp = call(
            api.move_to,
            (sphere[0], sphere[1], max(0.014, sphere[2] - depth)),
        )
        call(api.set_gripper, True)

        # Test the grasp before moving toward the basket rim.
        reached = call(
            api.move_to,
            (grasp[0], grasp[1], max(0.075, grasp[2] + 0.05)),
        )
        lifted = call(api.object_position)
        commanded_lift = reached[2] - grasp[2]
        follows = (
            commanded_lift > 0.025
            and lifted[2] - sphere[2] > 0.55 * commanded_lift
            and lifted[2] > 0.045
            and math.hypot(lifted[0] - reached[0],
                           lifted[1] - reached[1]) < 0.035
        )
        if not follows:
            continue

        reached = call(
            api.move_to, (reached[0], reached[1], travel_z)
        )
        lifted = call(api.object_position)
        if (
            lifted[2] - 0.024 < basket[2] + 0.095
            or math.hypot(lifted[0] - reached[0],
                          lifted[1] - reached[1]) > 0.035
        ):
            continue

        offset = tuple(lifted[i] - reached[i] for i in range(3))
        target_x = basket[0] - offset[0]
        target_y = basket[1] - offset[1]
        start = reached
        distance = math.hypot(target_x - start[0], target_y - start[1])

        # Use short, settled transfers with object feedback. Reserve calls
        # for placement, release, retraction, and success verification.
        desired_steps = max(1, math.ceil(distance / 0.045))
        steps = min(desired_steps, (remaining - 6) // 2)
        if steps < 1:
            break

        held = True
        for step in range(1, steps + 1):
            fraction = step / steps
            reached = call(
                api.move_to,
                (
                    start[0] + fraction * (target_x - start[0]),
                    start[1] + fraction * (target_y - start[1]),
                    travel_z,
                ),
            )
            observed = call(api.object_position)
            error = math.sqrt(sum(
                (observed[i] - reached[i] - offset[i]) ** 2
                for i in range(3)
            ))
            if (
                error > 0.025
                or observed[2] - 0.024 < basket[2] + 0.095
            ):
                held = False
                break

        if not held:
            continue

        # Account for small shifts within the grasp. Release near the
        # basket floor, with the sphere's nominal top below the rim.
        offset = tuple(observed[i] - reached[i] for i in range(3))
        reached = call(
            api.move_to,
            (
                basket[0] - offset[0],
                basket[1] - offset[1],
                basket[2] + 0.052 - offset[2],
            ),
        )
        call(api.set_gripper, False)
        reached = call(
            api.move_to, (reached[0], reached[1], travel_z)
        )
        if call(api.done):
            return

    # Leave the gripper open and clear after an unsuccessful attempt.
    if remaining and call(api.done):
        return
    if remaining:
        call(api.set_gripper, False)
    if remaining and reached is not None:
        call(api.move_to, (reached[0], reached[1], travel_z))
    if remaining:
        call(api.done)
