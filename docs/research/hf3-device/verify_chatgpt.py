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
print('verify-done')