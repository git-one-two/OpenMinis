#!/usr/bin/env python3
"""Drive the real Android fresh-shell path via adb-forwarded debug JSON-RPC.
Run on the PC, outside Minis' Agent shell: nested calls otherwise deadlock on
the conservative Agent mutex. Keep the app idle while this harness runs.
"""
import argparse
import collections
import json
import pathlib
import time
import urllib.error
import urllib.request
import uuid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--url", default="http://127.0.0.1:5321")
parser.add_argument("--samples", type=int, default=150)
parser.add_argument("--output", default="harmony-hf3-acceptance.json")
args = parser.parse_args()
if not 1 <= args.samples <= 1000:
    parser.error("--samples must be 1..1000")

session = "debug-hf3-" + uuid.uuid4().hex
rows = []

def execute(label, command, timeout=15):
    request = {"jsonrpc": "2.0", "id": len(rows) + 1,
               "method": "debug.shellExecute",
               "params": {"session": session, "strategy": "fresh",
                          "command": command, "timeout": timeout}}
    started = time.monotonic()
    try:
        req = urllib.request.Request(
            args.url, json.dumps(request).encode(),
            {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout + 15) as response:
            body = json.load(response)
        if "error" in body:
            result = {"error": body["error"]}
        else:
            result = body["result"]
    except (OSError, ValueError, urllib.error.URLError) as error:
        result = {"error": str(error)}
    row = {"case": label, "result": result,
           "wall_seconds": round(time.monotonic() - started, 3)}
    rows.append(row)
    pathlib.Path(args.output).write_text(
        json.dumps({"session": session, "rows": rows}, indent=2),
        encoding="utf-8")
    return result

for n in range(args.samples):
    result = execute("external-true", "/bin/true")
    if result.get("exit_code") != 0:
        print("FAIL sample", n + 1, json.dumps(result, ensure_ascii=False)[:300])
    elif (n + 1) % 25 == 0:
        print("Completed", n + 1, "/", args.samples)

path = "/tmp/minis-hf3-write-" + uuid.uuid4().hex
write = execute("silent-write-then-user-exit182",
                "printf x >> '" + path + "'; exit 182")
read = execute("verify-single-write",
               "IFS= read -r value < '" + path + "'; printf '%s' \"$value\"")
cleanup = execute("cleanup", "rm -f '" + path + "'")
normal_failure = execute("ordinary-user-failure", "exit 7")
timed_out = execute("timeout", "sleep 20", timeout=1)
alive = execute("after-timeout-alive", "printf alive")

counts = collections.Counter(
    str(row["result"].get("exit_code", "rpc-error"))
    for row in rows if row["case"] == "external-true")
checks = {
    "all_external_true_pass": counts.get("0", 0) == args.samples,
    "user_182_preserved": write.get("exit_code") == 182,
    "side_effect_not_duplicated": read.get("exit_code") == 0 and read.get("output") == "x",
    "cleanup_pass": cleanup.get("exit_code") == 0,
    "normal_failure_preserved": normal_failure.get("exit_code") == 7,
    "timeout_preserved": timed_out.get("exit_code") == 124,
    "shell_alive_after_timeout": alive.get("exit_code") == 0 and alive.get("output") == "alive",
}
summary = {"session": session, "samples": args.samples,
           "external_exit_counts": dict(counts), "checks": checks,
           "passed": all(checks.values()), "rows": rows}
pathlib.Path(args.output).write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps({k: v for k, v in summary.items() if k != "rows"},
                 ensure_ascii=False, indent=2))
raise SystemExit(0 if summary["passed"] else 1)
