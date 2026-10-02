#!/usr/bin/env python3
"""Compile the actual patched ARM64 helper against an injected ptrace backend."""
import pathlib
import re
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[1]
source = (root / "deps/proot/src/tracee/reg.c").read_text()
match = re.search(r"static int push_verified_arm64_regs\(.*?\n\}", source, re.S)
assert match, "Harmony helper is missing from the built PRoot source"
preamble = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <errno.h>
#include <sys/types.h>
#include <sys/uio.h>
#define PTRACE_SETREGSET 1
#define PTRACE_GETREGSET 2
#define NT_PRSTATUS 3
#define NT_ARM_SYSTEM_CALL 4
static uint64_t bank[34];
static int number, mode, sets, number_sets, gets;
static long fake_ptrace(int request, pid_t pid, int which, struct iovec *io) {
    assert(pid == 123);
    if (mode == 6) { errno = ESRCH; return -1; }
    if (which == NT_PRSTATUS) {
        assert(io->iov_len == sizeof(bank));
        if (request == PTRACE_SETREGSET) {
            sets++;
            if (mode != 3 && !(mode == 1 && sets == 1))
                memcpy(bank, io->iov_base, sizeof(bank));
        } else {
            gets++;
            memcpy(io->iov_base, bank, sizeof(bank));
            if (mode == 4) io->iov_len = 8;
            if (mode == 5) ((uint64_t *)io->iov_base)[33] ^= 0xff;
        }
    } else {
        assert(which == NT_ARM_SYSTEM_CALL);
        assert(io->iov_len == sizeof(int));
        if (request == PTRACE_SETREGSET) {
            number_sets++;
            if (!(mode == 2 && number_sets == 1))
                memcpy(&number, io->iov_base, sizeof(number));
        } else memcpy(io->iov_base, &number, sizeof(number));
    }
    return 0;
}
#define ptrace fake_ptrace
"""
tests = r"""
static void reset(int m) {
    memset(bank, 0, sizeof(bank));
    number = 0; mode = m; sets = number_sets = gets = 0; errno = 0;
}
int main(void) {
    uint64_t wanted[34];
    for (int i = 0; i < 34; i++) wanted[i] = i + 99;
    reset(0);
    assert(push_verified_arm64_regs(123, wanted, sizeof(wanted), -1, true) == 0);
    assert(sets == 1 && number_sets == 1 && number == -1);
    reset(1);
    assert(push_verified_arm64_regs(123, wanted, sizeof(wanted), 222, true) == 0);
    assert(sets == 2 && number == 222 && memcmp(bank, wanted, sizeof(bank)) == 0);
    reset(2);
    assert(push_verified_arm64_regs(123, wanted, sizeof(wanted), 222, true) == 0);
    assert(sets == 2 && number_sets == 2 && number == 222);
    reset(3);
    assert(push_verified_arm64_regs(123, wanted, sizeof(wanted), -1, true) == -1);
    assert(sets == 3 && errno == EIO);
    reset(4);
    assert(push_verified_arm64_regs(123, wanted, sizeof(wanted), 0, false) == -1);
    assert(errno == EIO);
    reset(5);
    assert(push_verified_arm64_regs(123, wanted, sizeof(wanted), 0, false) == 0);
    assert(sets == 1 && number_sets == 0);
    reset(6);
    assert(push_verified_arm64_regs(123, wanted, sizeof(wanted), 0, false) == -1);
    assert(errno == ESRCH && sets == 0);
    reset(0);
    assert(push_verified_arm64_regs(123, wanted, 8, 0, false) == -1);
    assert(errno == EINVAL && sets == 0);
    return 0;
}
"""
with tempfile.TemporaryDirectory() as tmp:
    c = pathlib.Path(tmp) / "verify.c"
    binary = pathlib.Path(tmp) / "verify"
    c.write_text(preamble + match.group(0) + tests)
    subprocess.run(["cc", "-std=c99", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined", str(c), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
print("PASS: 8 injected regset scenarios (including negative syscall and wrong-iovec regression)")
