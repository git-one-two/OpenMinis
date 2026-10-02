# hf3-device — ChatGPT 修复版 APK 真机复测（2026-10-02）

> **上传说明**：本目录收录对 ChatGPT 覆盖更新 APK 的崩溃率复测证据。设备=华为 HarmonyOS ROM / kernel 5.10.43 aarch64（App `com.openminis.app.dev`，OpenMinis 1.14）。
> **复跑方法**：沙盒会话内 `python3 verify_chatgpt.py`（脚本自含：80 次直跑、10 次 shebang 采样、运行中 APK 内 proot/loader 哈希采集；结果固定写 `/var/minis/shared/work/OpenMinis-investigation/VERIFY_2026-10-02_chatgpt.md`）。
> **环境前提**：PROOT_VERBOSE 已删除（本次复测时 `<unset>`）；无任何密钥/token 参与。
> **解读**：见 VERIFY 文档——APK 内 `libproot.so` 已从 270,680B → 271,080B（= reg.c 候选补丁编入），但 `libproot-loader.so` 哈希未变（44ef39c1…）；崩溃率 8/80 全 182（基线 8/150≈5%），**判：未解决**，与定案文档 §4.1 预测一致（补丁拦机制 b、真机主要暴露机制 a）。下一步=定案文档 §4.2 App 层 182 安全重试。

---
## env
PROOT_VERBOSE=<unset>
## APK 内二进制（正在运行的 App）
- lib/arm64-v8a/libproot-loader.so: 44ef39c1e1a18c09 len=18136 (tracer=False)
- lib/arm64-v8a/libproot.so: 07f497b1f2b0446e len=271080 (tracer=False)
## A. /bin/true direct execve: total=80 fail=8
基线参考: 8/150(全182)、21/300(静态PIE)、8/200(动态PIE)
- miss i=19 rc=182
- miss i=28 rc=182
- miss i=34 rc=182
- miss i=47 rc=182
- miss i=51 rc=182
- miss i=62 rc=182
- miss i=64 rc=182
- miss i=65 rc=182
- shebang miss i=7 rc=182
## B. shebang direct execve: total=10 fail=1 (基线曾 ~100% EFAULT / 近测 0/12)
## 判定口径
A fail=0 且 B fail=0 且 会话内无 182 → 修复生效；A fail 与基线相近 → 未解决
时间: 2026-10-02 14:01:19
## 附件2 采集脚本 verify_chatgpt.py（原样收录，可复跑）

```python
import os, subprocess, hashlib, zipfile, json, glob

D = '/var/minis/shared/work/OpenMinis-investigation'
OUT = D + '/VERIFY_2026-10-02_chatgpt.md'
r = open(OUT, 'w')
def say(s):
    r.write(s + '\n'); r.flush()

# 0. env state
v = os.environ.get('PROOT_VERBOSE')
say('## env\nPROOT_VERBOSE=%s' % ('<unset>' if v is None else v))

# 1. find running app APK via /proc fds, hash the proot/loader from it
found = {}
for pid in os.listdir('/proc'):
    if not pid.isdigit(): continue
    try:
        cl = open('/proc/%s/cmdline' % pid, 'rb').read().decode('utf-8', 'replace')
        if 'com.openminis.app.dev' not in cl and 'libproot' not in cl: continue
        is_proot = 'libproot' in cl
    except Exception: continue
    for fd in os.listdir('/proc/%s/fd' % pid):
        try:
            t = os.readlink('/proc/%s/fd/%s' % (pid, fd))
        except Exception: continue
        if t != '/data/app/' and not t.endswith('base.apk'): continue
        try:
            z = zipfile.ZipFile('/proc/%s/fd/%s' % (pid, fd))
        except Exception: continue
        for name in ('lib/arm64-v8a/libproot-loader.so', 'lib/arm64-v8a/libproot.so'):
            try:
                data = z.read(name)
            except KeyError: continue
            h = hashlib.sha256(data).hexdigest()[:16] + ' len=%d' % len(data)
            if name not in found:
                found[name] = (h, is_proot, cl[:40])
if found:
    say('## APK 内二进制（正在运行的 App）')
    for k, v2 in found.items():
        say('- %s: %s (tracer=%s)' % (k, v2[0], v2[1]))
else:
    say('## APK 内二进制: 未找到（fd 不含 base.apk？）')

# 2. crash rate: /bin/true x80 (direct execve, ET_DYN via loader)
n = f = c182 = 0
misses = []
for i in range(80):
    n += 1
    try:
        rc = subprocess.run(['/bin/true'], capture_output=True, timeout=20).returncode
    except Exception:
        rc = -1
    if rc != 0:
        f += 1
        misses.append('miss i=%d rc=%d' % (i, rc))
say('## A. /bin/true direct execve: total=%d fail=%d' % (n, f))
say('基线参考: 8/150(全182)、21/300(静态PIE)、8/200(动态PIE)')
for m in misses[:20]: say('- ' + m)

# 3. shebang x10
sb = open('/tmp/sbtest2.sh', 'w')
sb.write('#!/bin/sh\nexit 0\n'); sb.close()
os.chmod('/tmp/sbtest2.sh', 0o755)
s = sf = 0
for i in range(10):
    s += 1
    try:
        rc = subprocess.run(['/tmp/sbtest2.sh'], capture_output=True, timeout=20).returncode
    except Exception:
        rc = -1
    if rc != 0:
        sf += 1
        say('- shebang miss i=%d rc=%d' % (i, rc))
say('## B. shebang direct execve: total=%d fail=%d (基线曾 ~100%% EFAULT / 近测 0/12)' % (s, sf))

say('## 判定口径')
say('A fail=0 且 B fail=0 且 会话内无 182 → 修复生效；A fail 与基线相近 → 未解决')
say('时间: ' + subprocess.run(['date', '+%F %T'], capture_output=True, text=True).stdout.strip())
r.close()
print('verify-done')```
