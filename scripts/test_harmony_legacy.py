#!/usr/bin/env python3
"""Compatibility smoke tests for the August source/loader protocol on Linux ARM64."""
import collections, hashlib, json, os, pathlib, platform, shutil, subprocess, tempfile
root = pathlib.Path(__file__).resolve().parents[1]
assert platform.machine() == "aarch64"
source = root / "deps/legacy-source"
header = source / "src/linux/ashmem.h"
header.parent.mkdir(exist_ok=True)
header.write_text("#include <sys/ioctl.h>\n#define ASHMEM_SET_SIZE _IOW(0x77,3,unsigned long)\n#define ASHMEM_GET_SIZE _IO(0x77,4)\n")
subprocess.run(["make","-j4","CC=clang -fuse-ld=lld"],cwd=source/"src",check=True)
proot = str(source / "src/proot")
results = []
with tempfile.TemporaryDirectory(prefix="legacy-proot-") as tmp:
    tmp = pathlib.Path(tmp)
    loader = tmp / "loader"
    shutil.copyfile(root/"deps/harmony-legacy/libproot-loader.so",loader)
    loader.chmod(0o755)
    script = tmp / "script.sh"
    script.write_text('#!/bin/sh\nprintf "%s" "$1"\n')
    script.chmod(0o755)
    child = tmp / "child.py"
    child.write_text('''import collections,json,pathlib,subprocess,sys
script,marker=sys.argv[1:]
quote="a b'\\n中文 $ x"
cases=[("true",["/bin/true"],400),("shebang",[script,quote],40),("user182",["/bin/sh","-c",'printf x >> "$1"; exit 182',"sh",marker],40)]
rows=[]
for name,command,count in cases:
 for _ in range(count):
  try:
   p=subprocess.run(command,capture_output=True,text=True,timeout=10)
   rows.append({"case":name,"exit":p.returncode,"stdout":p.stdout,"stderr":p.stderr[:500]})
  except OSError as e:rows.append({"case":name,"exit":None,"error":str(e)})
writes=pathlib.Path(marker).read_text() if pathlib.Path(marker).exists() else ""
checks={"true":all(r["exit"]==0 for r in rows if r["case"]=="true"),"shebang":all(r["exit"]==0 and r["stdout"]==quote for r in rows if r["case"]=="shebang"),"user182":all(r["exit"]==182 for r in rows if r["case"]=="user182"),"writes_once":writes=="x"*40}
print(json.dumps({"checks":checks,"passed":all(checks.values()),"rows":rows}))
''')
    for seccomp in (True,False):
        env=os.environ.copy()
        env["PROOT_LOADER"]=str(loader)
        for key in ("PROOT_VERIFY_REGSET","PROOT_EXEC_LOADER_RETRY","PROOT_EXEC_DIAG_FILE","PROOT_NO_SECCOMP"):
            env.pop(key,None)
        if not seccomp:env["PROOT_NO_SECCOMP"]="1"
        p=subprocess.run([proot,"--link2symlink","/usr/bin/python3",str(child),str(script),str(tmp/("marker-"+str(seccomp)))],env=env,capture_output=True,text=True,timeout=240)
        try:r=json.loads(p.stdout)
        except ValueError:r={"passed":False,"stdout":p.stdout,"stderr":p.stderr}
        r.update(seccomp=seccomp,outer_exit=p.returncode)
        results.append(r)
        print("LEGACY_GROUP",seccomp,p.returncode,r.get("checks"),flush=True)
report={"source":"8cf13e997cdc9472997aae19df8050c073c9a86c","loader_sha256":hashlib.sha256(loader.read_bytes()).hexdigest() if loader.exists() else "12d2b63e897fd91a334fce23edea5d2419cae4d5fd2a369f05d03ab75682add0","groups":results,"passed":all(r["passed"] and r["outer_exit"]==0 for r in results),"scope":"Linux ARM64 source/loader protocol only. The APK's original Android binary is checked by SHA256; Huawei device validation remains pending."}
(root/"harmony-legacy-results.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
raise SystemExit(0 if report["passed"] else 1)
