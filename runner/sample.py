"""Parameter boxes and samplers. A box is {"dx": (lo, hi), "dy": (lo, hi), "yaw": (lo, hi)}; yaw in deg."""
from __future__ import annotations

import itertools
import math

import numpy as np
from scipy.stats import qmc

PARAMS = ("dx", "dy", "yaw")


def local_box() -> dict:
    return {"dx": (-0.05, 0.05), "dy": (-0.05, 0.05), "yaw": (-15.0, 15.0)}


def deploy_box() -> dict:
    # dy < ~-0.08 puts the sphere inside the basket wall (basket sits 0.23 m in -y); see sim/README.md.
    # yaw is a null dimension for a sphere but is still sampled.
    return {"dx": (-0.20, 0.20), "dy": (-0.08, 0.20), "yaw": (-90.0, 90.0)}


def sample_box(box: dict, n: int, method: str = "sobol", seed: int = 0) -> list[dict]:
    """n param dicts inside box; each gets seed = seed + i."""
    names = [k for k in PARAMS if k in box] + [k for k in box if k not in PARAMS]
    lo = np.array([box[k][0] for k in names], dtype=float)
    hi = np.array([box[k][1] for k in names], dtype=float)
    d = len(names)

    if method == "sobol":
        # random_base2 wants a power of two; draw the next one up and truncate.
        m = max(0, math.ceil(math.log2(max(n, 1))))
        unit = qmc.Sobol(d=d, scramble=True, seed=seed).random_base2(m)[:n]
    elif method == "uniform":
        unit = np.random.default_rng(seed).random((n, d))
    elif method == "grid":
        k = max(1, math.ceil(n ** (1 / d)))
        axis = np.linspace(0.0, 1.0, k) if k > 1 else np.array([0.5])
        unit = np.array(list(itertools.product(axis, repeat=d)))[:n]
    else:
        raise ValueError(f"unknown method {method!r}")

    pts = qmc.scale(unit, lo, hi) if len(unit) else unit
    return [{**{k: round(float(v), 6) for k, v in zip(names, row)}, "seed": seed + i}
            for i, row in enumerate(pts)]
