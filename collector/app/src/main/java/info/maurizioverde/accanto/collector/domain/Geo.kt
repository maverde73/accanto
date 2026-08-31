package info.maurizioverde.accanto.collector.domain

import kotlin.math.asin
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.sin
import kotlin.math.sqrt

/** Distance and movement decisions. Pure, so it can be tested without a device. */
object Geo {

    private const val EARTH_RADIUS_M = 6_371_008.8

    data class Fix(
        val epochMillis: Long,
        val lat: Double,
        val lon: Double,
        val accuracyM: Float?,
    )

    fun distanceM(a: Fix, b: Fix): Double {
        val lat1 = Math.toRadians(a.lat)
        val lat2 = Math.toRadians(b.lat)
        val dLat = lat2 - lat1
        val dLon = Math.toRadians(b.lon - a.lon)
        val h = sin(dLat / 2) * sin(dLat / 2) +
            cos(lat1) * cos(lat2) * sin(dLon / 2) * sin(dLon / 2)
        return 2 * EARTH_RADIUS_M * asin(min(1.0, sqrt(h)))
    }

    /**
     * Whether a new fix is worth storing.
     *
     * Indoors a GPS fix drifts by tens of metres while the phone lies still on a
     * table. Storing that would fill the outbox with fake movement and, worse,
     * make the map show someone wandering their own living room. So a fix is
     * kept only if it moved meaningfully, or if enough time passed that a fresh
     * confirmation is worth having anyway.
     */
    fun shouldStore(
        previous: Fix?,
        candidate: Fix,
        minMoveMeters: Double = 40.0,
        maxAgeMillis: Long = 10 * 60_000,
    ): Boolean {
        if (previous == null) return true
        if (candidate.epochMillis - previous.epochMillis >= maxAgeMillis) return true

        val moved = distanceM(previous, candidate)

        // Do not call it movement if it is smaller than the fix's own
        // uncertainty: that is noise wearing the costume of a journey.
        val noiseFloor = (candidate.accuracyM ?: 0f).toDouble()
        return moved >= maxOf(minMoveMeters, noiseFloor)
    }

    /**
     * Whether the move is large enough to count as Tier B evidence that the
     * person is moving, as opposed to merely a new position worth recording.
     */
    fun isMovementEvidence(previous: Fix?, candidate: Fix, thresholdMeters: Double = 75.0): Boolean {
        if (previous == null) return false
        val moved = distanceM(previous, candidate)
        val noiseFloor = (candidate.accuracyM ?: 0f).toDouble()
        return moved >= maxOf(thresholdMeters, noiseFloor * 2)
    }
}
