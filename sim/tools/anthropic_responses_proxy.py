"""Local OpenAI-Responses -> Anthropic-Messages proxy, so the Ditto agent loop can drive Opus live.

  .venv/bin/python -m sim.tools.anthropic_responses_proxy   # listens on 127.0.0.1:8765
The agent loop (llms-for-robot-control ResponsesBackend) is unchanged; sim/opus_live.json points llm.base_url here.
Translates: instructions -> system; input_text/input_image -> text/image blocks; function_call /
function_call_output -> tool_use / tool_result; tools -> input_schema; tool_choice -> auto (no parallel; Opus 5.5 rejects forced tool choice).
Reasoning items are dropped (no extended thinking: Anthropic does not allow it with forced tool use).
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORT = 8765


def _creds():
    env = {}
    for line in (ROOT / "llms-for-robot-control" / "credentials.env").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _content_blocks(content):
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    blocks = []
    for part in content or []:
        t = part.get("type")
        if t in ("input_text", "output_text", "text"):
            blocks.append({"type": "text", "text": part.get("text", "")})
        elif t == "input_image":
            url = part.get("image_url") or ""
            header, _, data = url.partition(",")
            media = header.removeprefix("data:").split(";")[0] or "image/png"
            blocks.append({"type": "image", "source": {"type": "base64", "media_type": media, "data": data}})
    return blocks


def to_anthropic(body: dict) -> dict:
    messages = []

    def push(role, blocks):
        if not blocks:
            return
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"].extend(blocks)
        else:
            messages.append({"role": role, "content": list(blocks)})

    for item in body.get("input", []):
        t = item.get("type")
        if t == "reasoning":
            continue
        if t == "function_call":
            push("assistant", [{"type": "tool_use", "id": item["call_id"], "name": item["name"],
                                "input": json.loads(item.get("arguments") or "{}")}])
        elif t == "function_call_output":
            out = item.get("output")
            push("user", [{"type": "tool_result", "tool_use_id": item["call_id"],
                           "content": out if isinstance(out, str) else json.dumps(out)}])
        else:  # message (user / assistant / developer / system)
            role = "assistant" if item.get("role") == "assistant" else "user"
            push(role, _content_blocks(item.get("content")))
    # tool_result blocks must come first in their user message
    for m in messages:
        if m["role"] == "user":
            m["content"].sort(key=lambda b: b["type"] != "tool_result")
    tools = [{"name": t["name"], "description": t.get("description", ""),
              "input_schema": t.get("parameters") or {"type": "object", "properties": {}}}
             for t in body.get("tools", []) if t.get("type", "function") == "function"]
    out = {"model": body["model"], "max_tokens": int(body.get("max_output_tokens") or 8192),
           "messages": messages, "tools": tools}
    if body.get("instructions"):
        out["system"] = body["instructions"]
    if tools:
        # claude-opus-5-5 rejects tool_choice "any"/"tool"; "auto" + the framework's own format repair
        # (it re-asks when a reply has no tool call) stands in for "required".
        out["tool_choice"] = {"type": "auto", "disable_parallel_tool_use": body.get("parallel_tool_calls") is False}
    return out


def to_responses(data: dict) -> dict:
    output, text = [], []
    for block in data.get("content", []):
        if block.get("type") == "text":
            text.append(block["text"])
        elif block.get("type") == "tool_use":
            output.append({"type": "function_call", "id": "fc_" + block["id"], "call_id": block["id"],
                           "name": block["name"], "arguments": json.dumps(block.get("input", {})),
                           "status": "completed"})
    if text:
        output.insert(0, {"type": "message", "id": "msg_" + uuid.uuid4().hex, "role": "assistant",
                          "status": "completed", "content": [{"type": "output_text", "text": "".join(text)}]})
    u = data.get("usage", {})
    usage = {"input_tokens": int(u.get("input_tokens", 0)), "output_tokens": int(u.get("output_tokens", 0))}
    usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]
    return {"id": data.get("id", "resp_" + uuid.uuid4().hex), "object": "response", "status": "completed",
            "model": data.get("model"), "output": output, "usage": usage}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        raw = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):  # noqa: N802
        if not self.path.rstrip("/").endswith("/responses"):
            return self._send(404, {"error": {"message": f"unsupported path {self.path}"}})
        body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))))
        env = _creds()
        headers = {"x-api-key": env["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
        if env.get("ANTHROPIC_WORKSPACE_ID"):
            headers["anthropic-workspace-id"] = env["ANTHROPIC_WORKSPACE_ID"]
        req = urllib.request.Request("https://api.anthropic.com/v1/messages",
                                     data=json.dumps(to_anthropic(body)).encode(), headers=headers)
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                data = json.loads(r.read())
        except urllib.error.HTTPError as e:
            msg = e.read()[:2000].decode(errors="replace")
            print(f"[proxy] anthropic HTTP {e.code}: {msg}", file=sys.stderr, flush=True)
            return self._send(e.code, {"error": {"message": msg}})
        print(f"[proxy] ok {time.time() - t0:.1f}s stop={data.get('stop_reason')}", file=sys.stderr, flush=True)
        self._send(200, to_responses(data))

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
