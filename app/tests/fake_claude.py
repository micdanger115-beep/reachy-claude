#!/usr/bin/env python3
"""Ersatz fuer die Claude Code CLI in Tests. Verhalten ueber FAKE_CLAUDE_* steuerbar."""

import json
import os
import sys
import time
from pathlib import Path

prompt = sys.stdin.buffer.read().decode("utf-8")  # wie die echte CLI: UTF-8, unabhaengig vom System
log = os.environ.get("FAKE_CLAUDE_LOG")
if log:
    with Path(log).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"argv": sys.argv[1:], "stdin": prompt, "env": dict(os.environ)}) + "\n")

mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
if mode == "sleep":
    time.sleep(30)
if mode == "sleep_child":
    # wie die echte CLI, die Unterprozesse startet: das Kind muss beim Abbruch mit sterben
    import subprocess

    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    Path(os.environ["FAKE_CLAUDE_CHILD"]).write_text(str(child.pid), encoding="utf-8")
    time.sleep(60)
if mode == "max_turns":
    print(
        json.dumps(
            {"type": "result", "subtype": "error_max_turns", "is_error": True, "session_id": "abc-123-def"}
        )
    )
    sys.exit(0)
if mode == "crash":
    print("boom", file=sys.stderr)
    sys.exit(3)
if mode == "fail_resume" and "--resume" in sys.argv:
    print("No conversation found", file=sys.stderr)
    sys.exit(1)

session = "11111111-2222-3333-4444-555555555555"
if "--resume" in sys.argv:
    session = sys.argv[sys.argv.index("--resume") + 1]
elif mode == "fail_resume":
    session = "99999999-2222-3333-4444-555555555555"
print(
    json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": f"Ich habe `{prompt}` erledigt.\n\n```py\nprint(1)\n```\nSPRECHTEXT: Erledigt: {prompt}.",
            "session_id": session,
            "total_cost_usd": 0.01,
        }
    )
)
