#!/usr/bin/env python3
"""Run real ARM64 PRoot + the APK's pinned loader, with test-only mmap faults."""
import json
import os
import pathlib
import platform
import shutil
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
assert platform.machine() == 'aarch64', 'requires a real Linux ARM64 runner'
output = ROOT / 'harmony-native-results.json'
results = []
with tempfile.TemporaryDirectory(prefix='harmony-native-') as directory:
    directory = pathlib.Path(directory)
    source = directory / 'proot'
    shutil.copytree(ROOT / 'deps/proot', source, ignore=shutil.ignore_patterns('.git', '*.o', 'proot'))
    for patch in sorted((ROOT / 'deps/patches').glob('*.patch')):
        subprocess.run(['git', 'apply', str(patch.resolve())], cwd=source, check=True)
    header = source / 'src/linux/ashmem.h'
    header.parent.mkdir(exist_ok=True)
    # Build-only shim: Android ashmem is unused on the Linux test runner.
    header.write_text('#include <sys/ioctl.h>\n#define ASHMEM_SET_SIZE _IOW(0x77,3,unsigned long)\n#define ASHMEM_GET_SIZE _IO(0x77,4)\n')
    helper = source / 'src/execve/loader_retry.c'
    code = helper.read_text()
    anchor = '    /* This is the actual vendored loader'
    assert anchor in code
    # Faults enter the real pinned loader's FATAL path. This injection exists
    # solely in this disposable CI source tree; it is never packaged in an APK.
    injection = '''    const char *target = getenv("MINIS_TEST_FAULT_TARGET");
    const char *count = getenv("MINIS_TEST_FAULT_COUNT");
    if (number == PR_mmap && target != NULL && count != NULL
        && tracee->load_info != NULL
        && strcmp(tracee->load_info->raw_path, target) == 0
        && tracee->harmony_loader.retries < (unsigned) atoi(count)) {
        note(tracee, WARNING, INTERNAL, "[TEST-FAULT] attempt=%u", tracee->harmony_loader.retries);
        poke_reg(tracee, SYSARG_1, 1); /* MAP_FIXED requires page alignment. */
        return;
    }
'''
    code = code.replace(anchor, injection + anchor)
    helper.write_text(code)
    filter_path = source / 'src/syscall/seccomp.c'
    filters = filter_path.read_text()
    # mmap is normally not intercepted. Only this test build adds its stop.
    filters = filters.replace('static FilteredSysnum proot_sysnums[] = {',
        'static FilteredSysnum proot_sysnums[] = {\n    { PR_mmap, FILTER_SYSEXIT },')
    filter_path.write_text(filters)
    subprocess.run(['make', '-j4', 'CC=clang -fuse-ld=lld'], cwd=source / 'src', check=True)
    proot = str(source / 'src/proot')
    loader = ROOT / 'src/android/app/src/main/jniLibs/arm64-v8a/libproot-loader.so'
    copied_loader = directory / 'loader'
    shutil.copyfile(loader, copied_loader)
    copied_loader.chmod(0o755)
    script = directory / 'script.sh'
    script.write_text('#!/bin/sh\nprintf "%s" "$1"\n')
    script.chmod(0o755)
    child = directory / 'child.py'
    child.write_text('''import json, pathlib, subprocess, sys
case, target, marker = sys.argv[1:]
quoted = "a b'\\n中文 $ x"
command = [target] if case == 'true' else [target, quoted]
if case == 'user182':
    command = [target, '-c', 'printf x >> "$1"; exit 182', 'sh', marker]
rows = []
for _ in range(10):
    try:
        p = subprocess.run(command, capture_output=True, text=True, timeout=10)
        rows.append({'exit': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr})
    except OSError as e:
        rows.append({'error': str(e)})
print(json.dumps({'rows': rows, 'writes': pathlib.Path(marker).read_text() if pathlib.Path(marker).exists() else ''}))
''')
    for no_seccomp in (False, True):
        for faults in (0, 1, 3, 4):
            for case, target in (('true', '/bin/true'), ('shebang', str(script)), ('user182', '/bin/sh')):
                marker = directory / ('marker-' + str(no_seccomp) + '-' + str(faults) + '-' + case)
                env = os.environ.copy()
                env.update(PROOT_LOADER=str(copied_loader), PROOT_VERIFY_REGSET='1',
                           PROOT_EXEC_LOADER_RETRY='1', MINIS_TEST_FAULT_TARGET=target,
                           MINIS_TEST_FAULT_COUNT=str(faults))
                if no_seccomp:
                    env['PROOT_NO_SECCOMP'] = '1'
                else:
                    env.pop('PROOT_NO_SECCOMP', None)
                run = subprocess.run([proot, '/usr/bin/python3', str(child), case, target, str(marker)],
                                     env=env, capture_output=True, text=True, timeout=100)
                item = {'no_seccomp': no_seccomp, 'faults': faults, 'case': case,
                        'exit': run.returncode, 'stderr': run.stderr[-12000:]}
                try:
                    item.update(json.loads(run.stdout))
                except ValueError:
                    item['stdout'] = run.stdout
                expected = 182 if faults == 4 or case == 'user182' else 0
                expected_output = "a b'\n中文 $ x" if case == 'shebang' and faults < 4 else ''
                expected_writes = 'x' * 10 if case == 'user182' and faults < 4 else ''
                item['passed'] = (run.returncode == 0 and len(item.get('rows', [])) == 10
                    and all(row.get('exit') == expected and row.get('stdout') == expected_output
                            for row in item.get('rows', []))
                    and item.get('writes') == expected_writes
                    and run.stderr.count('[TEST-FAULT]') == min(faults, 4) * 10)
                results.append(item)
                output.write_text(json.dumps(results, ensure_ascii=False, indent=2))
                print(json.dumps({k: v for k, v in item.items() if k not in ('rows', 'stderr')}, ensure_ascii=False), flush=True)
                if not item['passed']:
                    print(item['stderr'], flush=True)
assert all(item['passed'] for item in results), 'real native recovery integration failed'