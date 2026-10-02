package com.openminis.app.sandbox

import java.io.File
import java.util.concurrent.TimeUnit
import org.junit.Assert.*
import org.junit.Test

class LoaderStartupRetryPolicyTest {
    @Test fun startupLoaderExitAndRawWaitStatusRetry() {
        assertTrue(LoaderStartupRetryPolicy.shouldRetry(182, 182, false, 0, false))
        assertTrue(LoaderStartupRetryPolicy.shouldRetry(182, 0xb600, false, 2, false))
        assertTrue(LoaderStartupRetryPolicy.shouldRetry(0xb600, null, false, 0, false))
    }

    @Test fun noReplayAfterUserCodeEvenIfSilentOrStatusMissing() {
        for (exit in listOf(182, 0xb600, 139, 135)) {
            assertFalse(LoaderStartupRetryPolicy.shouldRetry(exit, exit, true, 0, false))
        }
    }

    @Test fun boundedAndHonorsStopTimeoutAndSpawnFailure() {
        assertFalse(LoaderStartupRetryPolicy.shouldRetry(182, 182, false, 3, false))
        assertFalse(LoaderStartupRetryPolicy.shouldRetry(182, 182, false, 0, true))
        for (exit in listOf(124, 130, -1, 0, 1, 125, 137, 143, 139)) {
            assertFalse(LoaderStartupRetryPolicy.shouldRetry(exit, if (exit == 124) 182 else exit, false, 0, false))
        }
        assertEquals(listOf(0L, 50L, 200L), (0..2).map(LoaderStartupRetryPolicy::delayMs))
    }

    private fun runMarked(command: String, statusPath: String): Pair<Int, String> {
        val proc = ProcessBuilder("/bin/sh", "-c",
            ForegroundCommandGroup.markCommandStart(command, statusPath))
            .redirectErrorStream(true).start()
        assertTrue(proc.waitFor(5, TimeUnit.SECONDS))
        return proc.exitValue() to proc.inputStream.bufferedReader().readText()
    }

    @Test fun silentSideEffectThen182MustNotRetry() {
        val dir = java.nio.file.Files.createTempDirectory("loader-boundary").toFile()
        try {
            val status = File(dir, "status").path
            val write = File(dir, "write")
            val result = runMarked("printf x >> '$write'; exit 182", status)
            assertEquals(182, result.first)
            assertEquals("", result.second)
            assertEquals("x", write.readText())
            assertTrue(File("$status.started").exists())
            assertFalse(LoaderStartupRetryPolicy.shouldRetry(182, 182, true, 0, false))
        } finally { dir.deleteRecursively() }
    }

    @Test fun failedMarkerWritePreventsUserSideEffects() {
        val dir = java.nio.file.Files.createTempDirectory("loader-fail-closed").toFile()
        try {
            val write = File(dir, "write")
            val result = runMarked("printf x > '$write'", File(dir, "missing/status").path)
            assertEquals(125, result.first)
            assertFalse(write.exists())
        } finally { dir.deleteRecursively() }
    }

    @Test fun markerQuotingPreservesHeredocsPipelinesAndCommandExit() {
        val dir = java.nio.file.Files.createTempDirectory("loader-quoting").toFile()
        try {
            val status = File(dir, "a'b").path
            val result = runMarked("cat <<'EOF' | /bin/sh -c 'cat'\na & b\nEOF\nexit 7", status)
            assertEquals(7, result.first)
            assertEquals("a & b\n", result.second)
            assertEquals("started", File("$status.started").readText())
        } finally { dir.deleteRecursively() }
    }
}
