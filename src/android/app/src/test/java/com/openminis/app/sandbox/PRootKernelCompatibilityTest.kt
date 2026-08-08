package com.openminis.app.sandbox

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PRootKernelCompatibilityTest {
    @Test
    fun nativeOffloadArgumentIsAbsentWhenDisabledEvenWithRegisteredHandlers() {
        val argument = PRootKernel.buildNativeOffloadArgument(
            enabled = false,
            socketName = "native-offload",
            handlers = listOf("android-open", "minis-config"),
        )

        assertEquals(null, argument)
    }

    @Test
    fun nativeOffloadArgumentIsPresentOnlyForExplicitlyEnabledExperiment() {
        val argument = PRootKernel.buildNativeOffloadArgument(
            enabled = true,
            socketName = "native-offload",
            handlers = listOf("android-open", "minis-config"),
        )

        assertEquals("--native-offload=native-offload:android-open,minis-config", argument)
    }

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
