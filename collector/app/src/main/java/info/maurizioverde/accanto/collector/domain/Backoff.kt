package info.maurizioverde.accanto.collector.domain

import kotlin.math.min
import kotlin.math.pow

/**
 * Retry pacing for the uploader.
 *
 * Exponential with full jitter. The jitter is not decoration: without it every
 * collector that lost connectivity during the same outage would come back at
 * the same instant, and the backend would face a thundering herd exactly when
 * it had just recovered.
 *
 * The random source is injected so the policy stays deterministic under test.
 */
class Backoff(
    private val initialMillis: Long = 5_000,
    private val maxMillis: Long = 15 * 60_000,
    private val factor: Double = 2.0,
    private val random: (Long) -> Long = { bound -> if (bound <= 0) 0 else (0 until bound).random() },
) {

    /**
     * Delay before attempt number [attempt], counting the first retry as 1.
     * Returns zero for attempt 0, so the first send is immediate.
     */
    fun delayFor(attempt: Int): Long {
        require(attempt >= 0) { "attempt must not be negative" }
        if (attempt == 0) return 0

        val ceiling = min(
            maxMillis.toDouble(),
            initialMillis * factor.pow(attempt - 1),
        ).toLong()

        return random(ceiling)
    }

    /** Upper bound for an attempt, ignoring jitter. Useful for reasoning and tests. */
    fun ceilingFor(attempt: Int): Long {
        if (attempt == 0) return 0
        return min(maxMillis.toDouble(), initialMillis * factor.pow(attempt - 1)).toLong()
    }
}
