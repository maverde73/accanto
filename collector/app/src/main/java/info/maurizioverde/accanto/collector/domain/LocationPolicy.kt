package info.maurizioverde.accanto.collector.domain

/**
 * How hard the phone works for position.
 *
 * Precise tracking runs only while a caregiver actually has the map open. The
 * rest of the time the phone reports rarely and cheaply. Spending a monitored
 * person's battery on a screen nobody is looking at would shorten the very
 * device the whole system depends on.
 */
enum class LocationMode { IDLE, LIVE }

data class LocationSpec(
    val intervalMillis: Long,
    val minUpdateDistanceMeters: Float,
    val highAccuracy: Boolean,
)

object LocationPolicy {

    fun specFor(mode: LocationMode): LocationSpec = when (mode) {
        LocationMode.IDLE -> LocationSpec(
            intervalMillis = 15 * 60_000,
            minUpdateDistanceMeters = 100f,
            highAccuracy = false,
        )
        LocationMode.LIVE -> LocationSpec(
            intervalMillis = 5_000,
            minUpdateDistanceMeters = 0f,
            highAccuracy = true,
        )
    }

    /**
     * Live mode is expensive, so it expires on its own. If the caregiver closes
     * the tab without a clean disconnect, the phone must not keep burning GPS
     * until the battery dies.
     */
    const val LIVE_MODE_TTL_MILLIS = 10 * 60_000L

    fun liveModeExpired(enabledAtMillis: Long, nowMillis: Long): Boolean =
        nowMillis - enabledAtMillis >= LIVE_MODE_TTL_MILLIS
}
