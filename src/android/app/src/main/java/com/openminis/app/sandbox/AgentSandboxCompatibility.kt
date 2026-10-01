package com.openminis.app.sandbox

import android.content.Context
import com.openminis.app.BuildConfig
import com.openminis.app.logging.AppLogger

/**
 * Device-local stability policy for the Agent's fresh-process PRoot path.
 *
 * The personal .dev build defaults to the conservative path because the
 * HarmonyOS field device has demonstrated random fork/exec SIGBUS/SIGSEGV,
 * PRoot event-loop assertions, native-offload EFAULTs and process pressure.
 * Release builds keep upstream defaults unless self-healing proves necessary.
 */
internal object AgentSandboxCompatibility {
    private const val TAG = "AgentSandboxCompat"
    private const val PREFS = "agent_sandbox_compatibility"
    private const val KEY_FORCE_NO_SECCOMP = "force_no_seccomp"
    private const val KEY_DISABLE_NATIVE_OFFLOAD = "disable_native_offload"
    private const val KEY_DISABLE_FAKE_NETLINK = "disable_fake_netlink"
    private const val KEY_SERIALIZE_AGENT = "serialize_agent_shell"

    /** Personal dev build: avoid the unstable ptrace+seccomp path from command one. */
    fun forceNoSeccomp(context: Context): Boolean =
        prefs(context).getBoolean(KEY_FORCE_NO_SECCOMP, BuildConfig.DEV_TOOLS)

    /** Personal dev build: old stable fork also kept native-offload off by default. */
    fun nativeOffloadEnabled(context: Context): Boolean =
        !prefs(context).getBoolean(KEY_DISABLE_NATIVE_OFFLOAD, BuildConfig.DEV_TOOLS)

    /** fake-netlink is another custom ptrace extension; keep it out of the safe Agent path. */
    fun fakeNetlinkEnabled(context: Context): Boolean =
        !prefs(context).getBoolean(KEY_DISABLE_FAKE_NETLINK, BuildConfig.DEV_TOOLS)

    /** Avoid 4-5 simultaneous PRoot instances on the known-problem device. */
    fun serializeAgentCommands(context: Context): Boolean =
        prefs(context).getBoolean(KEY_SERIALIZE_AGENT, BuildConfig.DEV_TOOLS)

    fun rememberNoSeccomp(context: Context, reason: String) {
        prefs(context).edit().putBoolean(KEY_FORCE_NO_SECCOMP, true).apply()
        AppLogger.warning(TAG, "compatibility mode: PROOT_NO_SECCOMP=1 ($reason)")
    }

    fun rememberStrongMode(context: Context, reason: String) {
        prefs(context).edit()
            .putBoolean(KEY_FORCE_NO_SECCOMP, true)
            .putBoolean(KEY_DISABLE_NATIVE_OFFLOAD, true)
            .putBoolean(KEY_DISABLE_FAKE_NETLINK, true)
            .putBoolean(KEY_SERIALIZE_AGENT, true)
            .apply()
        AppLogger.warning(
            TAG,
            "strong compatibility mode: no-seccomp + no native-offload + no fake-netlink + serialized Agent ($reason)",
        )
    }

    fun isProotFatal(
        commandExitRecorded: Boolean,
        processExitCode: Int?,
    ): Boolean {
        if (commandExitRecorded) return false
        return normalizeSignalExit(processExitCode) in SeccompFallbackPolicy.RETRYABLE_EXIT_CODES
    }

    /**
     * Field evidence contains failure shapes where the host PRoot exits 1/255
     * while its own stderr names the real signal/assertion. Treat these as
     * sandbox instability too, but only for recovery/probing — never blindly
     * replay the interrupted user command.
     */
    fun isSuspiciousSandboxFailure(
        commandExitRecorded: Boolean,
        processExitCode: Int?,
        commandExitCode: Int,
        output: String,
    ): Boolean {
        if (isProotFatal(commandExitRecorded, processExitCode)) return true
        val lower = output.lowercase()
        if ("restart_how != ptrace_cont" in lower && "assertion" in lower) return true
        if ("proot warning: signal 6 received" in lower) return true
        if ("proot info: vpid 1: terminated with signal 11" in lower) return true
        if ("proot info: vpid 1: terminated with signal 7" in lower) return true
        if ("bad address" in lower && commandExitCode in setOf(126, 182, 255)) return true
        if (commandExitCode in setOf(135, 139, 182, 255) &&
            ("segmentation fault" in lower || "bus error" in lower)
        ) return true
        return false
    }

    fun signalName(processExitCode: Int?, output: String = ""): String {
        val lower = output.lowercase()
        if ("restart_how != ptrace_cont" in lower || "signal 6 received" in lower) return "SIGABRT/PRoot-assert"
        if ("signal 11" in lower || "segmentation fault" in lower) return "SIGSEGV"
        if ("signal 7" in lower || "bus error" in lower) return "SIGBUS"
        return SeccompFallbackPolicy.signalName(normalizeSignalExit(processExitCode))
            ?: "sandbox-fatal"
    }

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
