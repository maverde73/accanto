package info.maurizioverde.accanto.collector.domain

import java.time.Instant
import java.time.ZoneId
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter

/**
 * Timestamp formatting for the wire.
 *
 * The backend rejects a naive timestamp: without an offset it cannot be placed
 * on a timeline, and an event that lands an hour off would either look stale or
 * -- worse -- look fresher than it is.
 *
 * It also rejects anything more than ten minutes in the future, so a phone with
 * a badly wrong clock is caught at the door rather than pinning the headline
 * green forever.
 */
object Timestamps {

    private val formatter: DateTimeFormatter = DateTimeFormatter.ISO_OFFSET_DATE_TIME

    fun isoOffset(epochMillis: Long, zone: ZoneId = ZoneId.systemDefault()): String =
        ZonedDateTime.ofInstant(Instant.ofEpochMilli(epochMillis), zone).format(formatter)

    /** Whether the device clock is far enough ahead that the backend will refuse. */
    fun isImplausiblyFuture(epochMillis: Long, nowMillis: Long): Boolean =
        epochMillis - nowMillis > MAX_SKEW_MILLIS

    const val MAX_SKEW_MILLIS = 10 * 60 * 1000L
}
