#!/usr/bin/env python3
"""Stage the exact paired execution components from the retained August APK."""
import hashlib
import json
import pathlib
import shutil
root = pathlib.Path(__file__).resolve().parents[1]
source = root / "deps/harmony-legacy"
manifest = json.loads((source / "manifest.json").read_text())
target = root / "src/android/app/src/main/jniLibs/arm64-v8a"
assets = root / "src/android/app/src/main/assets"
target.mkdir(parents=True, exist_ok=True)
assets.mkdir(parents=True, exist_ok=True)
for name, wanted in manifest["sha256"].items():
    data = (source / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != wanted:
        raise SystemExit("Legacy component hash mismatch: " + name)
    if data[:4] != b"\x7fELF":
        raise SystemExit("Not ELF: " + name)
    shutil.copyfile(source / name, target / name)
    (target / name).chmod(0o755)
    print(name, len(data), wanted)
shutil.copyfile(source / "libproot.so", assets / "proot-aarch64")
(assets / "proot-aarch64").chmod(0o755)
