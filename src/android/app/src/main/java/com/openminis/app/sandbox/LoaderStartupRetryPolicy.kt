package com.openminis.app.sandbox

/** Retry only a loader death before the INNER shell reached any user code. */
internal object LoaderStartupRetryPolicy {
    const val MAX_RETRIES = 3

    fun isLoaderFatal(exitCode: Int?): Boolean = exitCode == 182 || exitCode == 0xb600

    fun shouldRetry(
        commandExit: Int,
        processExit: Int?,
        userCommandStarted: Boolean,
        retries: Int,
        stopped: Boolean,
    ): Boolean {
        if (stopped || userCommandStarted || retries >= MAX_RETRIES) return false
        if (commandExit == 124 || commandExit == 130 || commandExit == -1) return false
        return isLoaderFatal(commandExit) || isLoaderFatal(processExit)
    }

    fun delayMs(retries: Int): Long = when (retries) {
        0 -> 0L
        1 -> 50L
        else -> 200L
    }
}
