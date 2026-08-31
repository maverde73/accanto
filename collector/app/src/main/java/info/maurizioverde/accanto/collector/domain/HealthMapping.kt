package info.maurizioverde.accanto.collector.domain

/**
 * Turning what the watch recorded into what the presence model consumes.
 *
 * Kept free of Health Connect types so it can be tested on the JVM: the Android
 * reader converts first, and the decisions live here.
 */
object HealthMapping {

    data class HeartRateSample(val epochMillis: Long, val bpm: Int)

    data class StepsBucket(val startMillis: Long, val endMillis: Long, val count: Long)

    /** Physiologically implausible readings, usually a bad optical contact. */
    const val MIN_PLAUSIBLE_BPM = 25
    const val MAX_PLAUSIBLE_BPM = 240

    fun isPlausible(bpm: Int): Boolean = bpm in MIN_PLAUSIBLE_BPM..MAX_PLAUSIBLE_BPM

    /**
     * Filters and thins heart-rate samples before queueing.
     *
     * At one sample a minute a night's sync arrives as hundreds of readings.
     * They all matter for a trend, but not for presence, and shipping every one
     * over a metered connection is wasteful. Keeping at most one per interval
     * preserves the shape while cutting the volume.
     */
    fun thin(
        samples: List<HeartRateSample>,
        minSpacingMillis: Long = 60_000,
    ): List<HeartRateSample> {
        val usable = samples.filter { isPlausible(it.bpm) }.sortedBy { it.epochMillis }
        if (usable.isEmpty()) return emptyList()

        val kept = mutableListOf(usable.first())
        for (sample in usable.drop(1)) {
            if (sample.epochMillis - kept.last().epochMillis >= minSpacingMillis) kept.add(sample)
        }
        return kept
    }

    /**
     * Buckets with no steps are dropped: "zero steps" is not evidence of
     * movement, and queueing it would make a motionless hour look like data.
     */
    fun movementBuckets(buckets: List<StepsBucket>): List<StepsBucket> =
        buckets.filter { it.count > 0 }.sortedBy { it.endMillis }

    /**
     * The instant a steps bucket is attributed to.
     *
     * The end of the window, not the start: the person had certainly taken those
     * steps by then, whereas the start would claim movement possibly an hour
     * before it happened and could hold the headline green on stale data.
     */
    fun attributedInstant(bucket: StepsBucket): Long = bucket.endMillis
}
