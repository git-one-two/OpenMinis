# HarmonyOS Agent Sandbox Crash — Field Evidence (2026-10-01)

Source: on-device automated diagnosis from the user's `com.openminis.app.dev` build after upgrading to OpenMinis 1.14.

## Observed failure pattern

- Device/kernel: Huawei Android compatibility environment, Linux 5.10.43 aarch64.
- Sandbox: Alpine 3.21.3 under the app-bundled PRoot.
- Shell builtins such as `echo` were stable.
- External fork/exec commands such as `ls`, `cat`, `/bin/true`, `git`, `python3`, `dd` failed randomly at roughly 25–40% in repeated samples.
- Typical failures: SIGBUS / exit 135, SIGSEGV / exit 139, wrapper-specific 182/255, and `Bad address` / rc 126.
- PRoot itself twice hit:
  `tracee/event.c:568 assertion "tracee->restart_how != PTRACE_CONT" failed`
  followed by `proot warning: signal 6 received`.
- Non-PRoot paths (native app file I/O and built-in browser) remained healthy, isolating the incident to the PRoot execution layer.

## Runtime shape during the incident

Fresh Agent commands were launched with:

- `--link2symlink`
- `--native-offload=...`
- `--fake-netlink`
- `setsid /bin/sh -c ...`

Up to 4–5 PRoot instances were observed concurrently, including stale trees from timed-out commands. Android's per-app process budget queued at least one command.

The host was also under memory pressure: free memory stayed below roughly 0.5 GB and swap usage was high. This is treated as a possible amplifier, not a proven root cause.

## Source-level interpretation

The exact assertion is inside PRoot's seccomp-event path. `PROOT_NO_SECCOMP=1` prevents PRoot from enabling its syscall seccomp filter at launch, so it bypasses that event path entirely.

The device report also observed `/usr/local/bin/minis-debug: Bad address` while native-offload was present, making the custom execve interception path another high-priority suspect.

A third-party Android PRoot patch was found that replaces the same `restart_how != PTRACE_CONT` assertion flow with additional Android-specific exec/fork event handling. It is extensive and is NOT copied wholesale into this fork; it is retained as evidence that this assertion is a real Android compatibility edge, not an invented symptom.

## Hotfix policy for the personal dev build

For the Agent fresh-process path only:

1. Default to `PROOT_NO_SECCOMP=1`.
2. Default native-offload OFF.
3. Default fake-netlink OFF.
4. Serialize Agent PRoot commands to avoid 4–5 concurrent tracer trees amplifying process/memory pressure.
5. Keep `--link2symlink` because package/Git hardlink semantics depend on it.
6. Detect PRoot assertion, signal-6, vpid-1 SIGSEGV/SIGBUS, Bad-address and 135/139/182/255 crash signatures.
7. Never automatically replay a late-failing user command; it may already have side effects.
8. Run a side-effect-free repeated fork/exec + `apk --version` probe before declaring recovery.
9. Release/upstream builds keep normal OpenMinis defaults unless runtime self-healing proves necessary.

## Validation gate

A green CI build is necessary but not sufficient. Final acceptance requires the real device to repeat the previously failing class of long Agent task and pass sustained fork/exec stress without Bus error, SIGSEGV, PRoot assertion, or a wedged Agent.
