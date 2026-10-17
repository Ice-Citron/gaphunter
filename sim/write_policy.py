"""Ask Astra once to write policy.py against sim/api.py; cache it as results/policies/<version>.py.

  .venv/bin/python -m sim.write_policy v1
"""
from __future__ import annotations

import inspect
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CREDENTIALS = ROOT / "llms-for-robot-control" / "credentials.env"
MODEL = os.environ.get("GAPHUNTER_MODEL", "gpt-6-astra")

TASK = """You are writing the control policy for a peg-in-hole insertion cell.

A UR5e arm holds a square peg (20 x 20 mm, 80 mm long) pointing straight down. A block on the table
has a square hole (21 x 21 mm, 0.5 mm clearance per side, 50 mm deep); its top surface is at z = 0.05 m.
In our test cell the hole is placed at x = 0.45 +/- 0.05 m, y = 0.00 +/- 0.05 m, yaw = 0 +/- 15 degrees.
The trial succeeds when the peg is seated at least 30 mm deep in the hole with less than 1 mm lateral error.

Write a Python module that defines `def run(api):`. It is called once per trial and must return when
finished. `api` is the module below; use only these four functions (plus `math`, which you may import).
You have at most 300 API calls per trial. Contact force above 150 N aborts the trial as a collision.

```python
{api_source}
```

Reply with the complete module in a single ```python code block, followed by at most three sentences
explaining the strategy."""


def _credentials():
    env = {}
    for line in CREDENTIALS.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env.get("OPENAI_API_KEY") or os.environ["OPENAI_API_KEY"], \
        env.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")


def ask_astra(prompt: str) -> tuple[str, dict]:
    key, base = _credentials()
    body = {"model": MODEL, "input": prompt, "reasoning": {"effort": "medium"}, "store": False}
    req = urllib.request.Request(f"{base}/responses", data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    for attempt in range(3):  # retry 2x with backoff
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read())
            break
        except Exception as exc:  # noqa: BLE001
            if attempt == 2:
                raise
            print(f"Astra call failed ({exc}); retrying", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    text = data.get("output_text") or "".join(
        c.get("text", "") for item in data.get("output", []) if item.get("type") == "message"
        for c in item.get("content", []))
    return text, {"model": data.get("model", MODEL), "usage": data.get("usage")}


def main(version: str = "v1"):
    from sim import api
    prompt = TASK.replace("{api_source}", inspect.getsource(api))
    text, meta = ask_astra(prompt)
    match = re.search(r"```python\n(.*?)```", text, re.S)
    if not match:
        raise SystemExit(f"No code block in Astra's reply:\n{text}")
    out = ROOT / "results" / "policies"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{version}.py").write_text(match.group(1))
    (out / f"{version}.exchange.json").write_text(json.dumps(
        {"model": meta["model"], "usage": meta["usage"], "prompt": prompt, "response": text,
         "code": match.group(1), "policy_path": f"results/policies/{version}.py"}, indent=1))
    print(text)


if __name__ == "__main__":
    main(*sys.argv[1:])
