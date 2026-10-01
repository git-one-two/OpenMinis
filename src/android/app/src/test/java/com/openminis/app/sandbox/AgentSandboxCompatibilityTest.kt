package com.openminis.app.sandbox

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AgentSandboxCompatibilityTest {

    @Test
    fun normalizesRawSignalForms() {
        assertEquals(139, AgentSandboxCompatibility.normalizeSignalExit(11))
        assertEquals(139, AgentSandboxCompatibility.normalizeSignalExit(-11))
        assertEquals(135, AgentSandboxCompatibility.normalizeSignalExit(7))
        assertEquals(132, AgentSandboxCompatibility.normalizeSignalExit(4))
        assertEquals(159, AgentSandboxCompatibility.normalizeSignalExit(31))
    }

    @Test
    fun onlyStatuslessFatalProcessExitIsSandboxCrash() {
        assertTrue(
            AgentSandboxCompatibility.isProotFatal(
                commandExitRecorded = false,
                processExitCode = 139,
            ),
        )
        assertTrue(
            AgentSandboxCompatibility.isProotFatal(
                commandExitRecorded = false,
                processExitCode = 11,
            ),
        )
        assertFalse(
            AgentSandboxCompatibility.isProotFatal(
                commandExitRecorded = true,
                processExitCode = 139,
            ),
        )
        assertFalse(
            AgentSandboxCompatibility.isProotFatal(
                commandExitRecorded = false,
                processExitCode = 1,
            ),
        )
    }

    @Test
    fun recognizesFieldReportProotAssertion() {
        assertTrue(
            AgentSandboxCompatibility.isSuspiciousSandboxFailure(
                commandExitRecorded = false,
                processExitCode = 1,
                commandExitCode = 1,
                output = "./tracee/event.c:568: assertion \"tracee->restart_how != PTRACE_CONT\" failed\n" +
                    "proot warning: signal 6 received from process 44381",
            ),
        )
    }

    @Test
    fun recognizesRandomExternalBinaryCrashForRecoveryProbe() {
        assertTrue(
            AgentSandboxCompatibility.isSuspiciousSandboxFailure(
                commandExitRecorded = true,
                processExitCode = 0,
                commandExitCode = 139,
                output = "Segmentation fault (core dumped)",
            ),
        )
        assertTrue(
            AgentSandboxCompatibility.isSuspiciousSandboxFailure(
                commandExitRecorded = true,
                processExitCode = 0,
                commandExitCode = 126,
                output = "/bin/sh: minis-debug: Bad address",
            ),
        )
    }

    @Test
    fun normalUserFailureIsNotSandboxInstability() {
        assertFalse(
            AgentSandboxCompatibility.isSuspiciousSandboxFailure(
                commandExitRecorded = true,
                processExitCode = 0,
                commandExitCode = 1,
                output = "git: repository not found",
            ),
        )
    }
}
