package info.maurizioverde.accanto.collector.data

import info.maurizioverde.accanto.collector.data.db.OutboxEvent
import info.maurizioverde.accanto.collector.data.db.OutboxLocation
import info.maurizioverde.accanto.collector.data.net.EventDto
import info.maurizioverde.accanto.collector.data.net.LocationDto
import info.maurizioverde.accanto.collector.domain.DedupKey
import info.maurizioverde.accanto.collector.domain.EventKind
import info.maurizioverde.accanto.collector.domain.Source
import info.maurizioverde.accanto.collector.domain.Timestamps
import java.time.ZoneId
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject

/**
 * Pure conversions between what the sources observe, what the queue stores and
 * what goes on the wire. Kept free of Android types so it can be tested on the
 * JVM without a device.
 */
object Mapping {

    private val json = Json { ignoreUnknownKeys = true }

    fun toOutbox(
        subjectId: String,
        kind: EventKind,
        source: Source,
        occurredAtMillis: Long,
        payload: JsonObject = buildJsonObject { },
    ): OutboxEvent = OutboxEvent(
        occurredAtMillis = occurredAtMillis,
        source = source.code,
        kind = kind.code,
        payloadJson = payload.toString(),
        dedupKey = DedupKey.of(subjectId, source.code, kind.code, occurredAtMillis),
    )

    fun toOutboxLocation(
        subjectId: String,
        occurredAtMillis: Long,
        lat: Double,
        lon: Double,
        accuracyM: Float?,
        speedMps: Float?,
        batteryPct: Int?,
    ): OutboxLocation = OutboxLocation(
        occurredAtMillis = occurredAtMillis,
        lat = lat,
        lon = lon,
        accuracyM = accuracyM,
        speedMps = speedMps,
        batteryPct = batteryPct,
        dedupKey = DedupKey.forLocation(subjectId, occurredAtMillis),
    )

    fun toDto(event: OutboxEvent, zone: ZoneId = ZoneId.systemDefault()): EventDto = EventDto(
        occurredAt = Timestamps.isoOffset(event.occurredAtMillis, zone),
        source = event.source,
        kind = event.kind,
        payload = parsePayload(event.payloadJson),
        dedupKey = event.dedupKey,
    )

    fun toDto(fix: OutboxLocation, zone: ZoneId = ZoneId.systemDefault()): LocationDto = LocationDto(
        occurredAt = Timestamps.isoOffset(fix.occurredAtMillis, zone),
        lat = fix.lat,
        lon = fix.lon,
        accuracyM = fix.accuracyM,
        speedMps = fix.speedMps,
        batteryPct = fix.batteryPct,
    )

    /** A corrupt payload must not stop the whole batch: the event still carries
     *  its timestamp and kind, which is what the presence model actually uses. */
    private fun parsePayload(raw: String): JsonObject = runCatching {
        json.parseToJsonElement(raw) as? JsonObject ?: buildJsonObject { }
    }.getOrElse { buildJsonObject { } }
}
