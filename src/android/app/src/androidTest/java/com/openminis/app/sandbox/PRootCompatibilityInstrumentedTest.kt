package com.openminis.app.sandbox

import android.content.Context
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Device/network regression suite for the plain PRoot compatibility path.
 *
 * Run only on an Android ARM64 device with network access:
 * ./gradlew :app:connectedDebugAndroidTest \
 *   -Pandroid.testInstrumentationRunnerArguments.class=com.openminis.app.sandbox.PRootCompatibilityInstrumentedTest
 */
@RunWith(AndroidJUnit4::class)
class PRootCompatibilityInstrumentedTest {
    private lateinit var context: Context

    @Before
    fun setUp() = runBlocking {
        context = InstrumentationRegistry.getInstrumentation().targetContext
        PRootKernel.setNativeOffloadEnabled(context, false)
        PRootKernel.boot(context)
    }

    @After
    fun tearDown() {
        PRootKernel.setNativeOffloadEnabled(context, false)
    }

    @Test
    fun standardProotSupportsAlpineAndGitWorkflow() = runBlocking {
        assertSuccess("/bin/true")

        val uname = assertSuccess("uname -m")
        assertTrue("Unexpected architecture: ${uname.output}", uname.output.contains("aarch64"))

        assertSuccess("apk --version")
        assertSuccess("apk update", timeout = 180_000L)
        assertSuccess("apk add git", timeout = 300_000L)

        val git = assertSuccess("git --version")
        assertTrue(git.output.contains("git version"))
    }

    private suspend fun assertSuccess(
        command: String,
        timeout: Long = 60_000L,
    ): ShellExecutor.ShellResult {
        val result = ShellExecutor.execute(context, command, timeout)
        assertEquals("$command failed:\n${result.output}", 0, result.exitCode)
        return result
    }
}
