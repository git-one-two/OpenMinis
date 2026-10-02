#!/usr/bin/env python3
"""Compile the actual ARM64 loader recovery with an injected tracee/ELF backend."""
from pathlib import Path
import os, subprocess, tempfile
root = Path(__file__).resolve().parents[1]
source = (root / "deps/proot/src/execve/loader_retry.c").read_text()
# Replace only platform declarations/includes; all production function bodies run.
source = "\n".join(line for line in source.splitlines() if not line.startswith("#include"))
mock = (root / "scripts/fixtures/harmony_loader_mock.c").read_text()
cases = (root / "scripts/fixtures/harmony_loader_cases.c").read_text()
with tempfile.TemporaryDirectory() as temporary:
    path = Path(temporary)
    (path / "test.c").write_text(mock + source + cases)
    cc = os.environ.get("CC", "cc")
    subprocess.run([cc, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined", str(path / "test.c"),
                    "-o", str(path / "test")], check=True)
    subprocess.run([str(path / "test")], check=True)
