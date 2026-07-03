#!/usr/bin/env python3
"""
Runs INSIDE the isolated child process that executes your defense.py.
Only `api.py` (Verdict/SiegeContext/ToolkitProxy) is on this process's import
path — NOT the rest of the harness, not the crypto module, not any phase key.
Every tool call is a serialized RPC to the parent over stdin/stdout.
"""
import sys
import json
import importlib.util
from dataclasses import asdict
from pathlib import Path

# Only this file's own directory is importable — never the parent harness root.
sys.path.insert(0, str(Path(__file__).parent))
from api import SiegeContext, ToolkitProxy, Verdict


def _send(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _recv():
    line = sys.stdin.readline()
    if not line:
        raise EOFError("parent closed pipe")
    return json.loads(line)


def load_defense(path):
    spec = importlib.util.spec_from_file_location("student_defense", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    defense_path = sys.argv[1]
    baseline_path = sys.argv[2]
    baseline = json.loads(Path(baseline_path).read_text())

    tools = ToolkitProxy(_send, _recv)
    ctx = SiegeContext(tools, baseline)

    mod = load_defense(defense_path)
    mod.register(ctx)

    while True:
        msg = _recv()
        if msg["type"] == "shutdown":
            break
        if msg["type"] == "event":
            try:
                verdict = ctx.dispatch(msg["event"])
                if not isinstance(verdict, Verdict):
                    verdict = Verdict(alert=False, reason="handler returned non-Verdict")
            except Exception as e:
                verdict = Verdict(alert=False, reason=f"handler error: {e}")
            _send({"type": "verdict", "verdict": asdict(verdict)})


if __name__ == "__main__":
    main()
