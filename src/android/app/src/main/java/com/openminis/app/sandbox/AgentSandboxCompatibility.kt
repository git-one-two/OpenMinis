package com.openminis.app.sandbox

import android.content.Context
import com.openminis.app.logging.AppLogger

/**
 * Device-local self-healing state for the Agent's fresh-process PRoot path.
 *
 * This is intentionally scoped to Agent shell execution. Terminal/native host
 * integrations keep their normal 1.14 behaviour unless they independently
 * need a compatibility fix.
 */
internal object AgentSandboxCompatibility {
    private const val TAG = "AgentSandboxCompat"
    private const val PREFS = "agent_sandbox_compatibility"
    private const val KEY_FORCE_NO_SECCOMP = "force_no_seccomp"
    private const val KEY_DISABLE_NATIVE_OFFLOAD = "disable_native_offload"

    fun forceNoSeccomp(context: Context): Boolean =
        prefs(context).getBoolean(KEY_FORCE_NO_SECCOMP, false)

    fun nativeOffloadEnabled(context: Context): Boolean =
        !prefs(context).getBoolean(KEY_DISABLE_NATIVE_OFFLOAD, false)

    fun rememberNoSeccomp(context: Context, reason: String) {
        prefs(context).edit().putBoolean(KEY_FORCE_NO_SECCOMP, true).apply()
        AppLogger.warning(TAG, "compatibility mode: PROOT_NO_SECCOMP=1 ($reason)")
    }

    fun rememberPlainProot(context: Context, reason: String) {
        prefs(context).edit()
            .putBoolean(KEY_FORCE_NO_SECCOMP, true)
            .putBoolean(KEY_DISABLE_NATIVE_OFFLOAD, true)
            .apply()
        AppLogger.warning(
            TAG,
            "compatibility mode: PROOT_NO_SECCOMP=1 + native_offload disabled for Agent ($reason)",
        )
    }

    fun isProotFatal(
        commandExitRecorded: Boolean,
        processExitCode: Int?,
    ): Boolean {
        if (commandExitRecorded) return false
        return normalizeSignalExit(processExitCode) in SeccompFallbackPolicy.RETRYABLE_EXIT_CODES
    }

    fun signalName(processExitCode: Int?): String =
        SeccompFallbackPolicy.signalName(normalizeSignalExit(processExitCode))
            ?: "fatal-signal"

    internal fun normalizeSignalExit(exitCode: Int?): Int? = when (exitCode) {
        4, -4 -> 132
        7, -7 -> 135
        11, -11 -> 139
        31, -31 -> 159
        else -> exitCode
    }

    private fun prefs(context: Context) =
        context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
}
