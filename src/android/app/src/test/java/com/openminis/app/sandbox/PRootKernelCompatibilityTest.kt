package com.openminis.app.sandbox

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PRootKernelCompatibilityTest {
    @Test
    fun nativeCrashSignalsAreRecognizedForFallback() {
        assertTrue(PRootKernel.isNativeCrashExitCode(135))
        assertTrue(PRootKernel.isNativeCrashExitCode(139))
        assertFalse(PRootKernel.isNativeCrashExitCode(0))
        assertFalse(PRootKernel.isNativeCrashExitCode(124))
        assertEquals("SIGBUS", PRootKernel.signalName(135))
        assertEquals("SIGSEGV", PRootKernel.signalName(139))
    }
}
