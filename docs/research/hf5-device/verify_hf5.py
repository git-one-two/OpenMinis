#!/usr/bin/env python3
"""Run inside Minis' Agent shell. Never calls debug.shellExecute recursively."""
import argparse
import collections
import hashlib
import json
import os
import pathlib
import subprocess
import tempfile
import time
import zipfile

parser = argparse.ArgumentParser()
parser.add_argument("--samples", type=int, default=200)
parser.add_argument("--output", default="/var/minis/shared/work/OpenMinis-investigation/VERIFY_2026-10-02_hf5.json")
args = parser.parse_args()
diagnostic_path = pathlib.Path("/var/minis/shared/work/OpenMinis-investigation/HF5_exec_diag.log")
started_at = int(time.time())
try:
    diagnostic_offset = diagnostic_path.stat().st_size
except OSError:
    diagnostic_offset = 0
if not 1 <= args.samples <= 1000:
    parser.error("--samples must be 1..1000")
rows = []
def run(case, command):
    try:
        process = subprocess.run(command, capture_output=True, text=True, timeout=20)
        result = {"case": case, "exit": process.returncode, "stdout": process.stdout,
                  "stderr": process.stderr[:1000]}
    except (OSError, subprocess.TimeoutExpired) as error:
        result = {"case": case, "exit": None, "error": str(error)}
    rows.append(result)
    return result

flags = {key: os.environ.get(key) for key in ("PROOT_EXEC_LOADER_RETRY", "PROOT_VERIFY_REGSET", "PROOT_VERBOSE")}
for n in range(args.samples):
    run("nested-true", ["/bin/true"])
side_samples = 40
with tempfile.TemporaryDirectory(prefix="minis-hf5-") as directory:
    directory = pathlib.Path(directory)
    script = directory / "script.sh"
    script.write_text("#!/bin/sh\nprintf '%s' \"$1\"\n", encoding="utf-8")
    script.chmod(0o755)
    quoted = "a b'\n中文 $ x"
    for n in range(side_samples):
        run("shebang-argv", [str(script), quoted])
    marker = directory / "user-body"
    # This user program intentionally returns 182 AFTER writing.
    # Loader retries must neither rerun that write nor suppress the user exit.
    for n in range(side_samples):
        run("user-write-exit182", ["/bin/sh", "-c", 'printf x >> "$1"; exit 182', "sh", str(marker)])
    writes = marker.read_bytes() if marker.exists() else b""
    env = run("argv-env", ["/bin/sh", "-c",
        'printf "%s|%s|%s" "$1" "$PROOT_EXEC_LOADER_RETRY" "$PROOT_VERIFY_REGSET"', "sh", quoted])
    after = run("after-user182-alive", ["/bin/sh", "-c", "printf alive"])
counts = collections.Counter(str(row["exit"]) for row in rows if row["case"] == "nested-true")
checks = {
    "retry_environment_enabled": flags["PROOT_EXEC_LOADER_RETRY"] == "1" and flags["PROOT_VERIFY_REGSET"] == "1",
    "all_nested_true_pass": counts.get("0", 0) == args.samples,
    "shebang_argv_preserved": all(row["exit"] == 0 and row["stdout"] == quoted for row in rows if row["case"] == "shebang-argv"),
    "user182_preserved": all(row["exit"] == 182 for row in rows if row["case"] == "user-write-exit182"),
    "user_writes_exactly_once": writes == b"x" * side_samples,
    "argv_env_preserved": env["exit"] == 0 and env["stdout"] == quoted + "|1|1",
    "parent_still_alive": after["exit"] == 0 and after["stdout"] == "alive",
}
apk_hashes = {}
for pid in pathlib.Path("/proc").iterdir():
    if not pid.name.isdigit():
        continue
    try:
        command = (pid / "cmdline").read_bytes()
        if b"com.openminis.app.dev" not in command:
            continue
        for fd in (pid / "fd").iterdir():
            try:
                if not os.readlink(fd).endswith("base.apk"):
                    continue
                with zipfile.ZipFile(fd) as package:
                    for name in ("lib/arm64-v8a/libproot.so", "lib/arm64-v8a/libproot-loader.so"):
                        apk_hashes[name] = hashlib.sha256(package.read(name)).hexdigest()
                break
            except (OSError, KeyError, zipfile.BadZipFile):
                continue
    except OSError:
        continue
    if apk_hashes:
        break
expected_proot_sha256 = "b94022ea3374f38714bb7e023d51a3693d444d51fd4eccd6c2a5a52bd8f085ba"
checks["hf5_native_installed"] = apk_hashes.get("lib/arm64-v8a/libproot.so") == expected_proot_sha256
report = {"flags": flags, "samples": args.samples, "external_exit_counts": dict(counts),
          "writes": len(writes), "checks": checks, "passed": all(checks.values()),
          "apk_hashes": apk_hashes, "rows": rows}
try:
    with diagnostic_path.open("rb") as diagnostic:
        diagnostic.seek(diagnostic_offset)
        native_log = diagnostic.read(131328).decode("utf-8", errors="replace")
    diagnostic_error = None
except OSError as error:
    native_log = ""
    diagnostic_error = str(error)
report["native_diagnostics"] = {
    "started_at": started_at, "ended_at": int(time.time()),
    "log": native_log, "read_error": diagnostic_error,
    "stages": dict(collections.Counter(
        line.split("stage=", 1)[1].split()[0] for line in native_log.splitlines() if "stage=" in line)),
}
output = pathlib.Path(args.output)
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({key: value for key, value in report.items() if key not in ("rows", "native_diagnostics")}, ensure_ascii=False, indent=2))
print("report:", output)
raise SystemExit(0 if report["passed"] else 1)
