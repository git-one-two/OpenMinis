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
}
