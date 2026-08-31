package info.maurizioverde.accanto.collector.data.net

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

/**
 * Wire contracts, mirroring `backend/app/schemas/ingest.py`.
 *
 * Timestamps go out as ISO-8601 **with an offset**: the backend rejects a naive
 * one, because a timestamp without a zone cannot be placed on a timeline and
 * would silently poison the presence model.
 */

@Serializable
data class EventDto(
    @SerialName("occurred_at") val occurredAt: String,
    val source: String,
    val kind: String,
    val confidence: Float = 1.0f,
    val payload: JsonObject,
    @SerialName("dedup_key") val dedupKey: String,
)

@Serializable
data class EventBatchDto(val events: List<EventDto>)

@Serializable
data class LocationDto(
    @SerialName("occurred_at") val occurredAt: String,
    val lat: Double,
    val lon: Double,
    @SerialName("accuracy_m") val accuracyM: Float? = null,
    @SerialName("speed_mps") val speedMps: Float? = null,
    @SerialName("battery_pct") val batteryPct: Int? = null,
)

@Serializable
data class LocationBatchDto(val fixes: List<LocationDto>)

@Serializable
data class HeartbeatDto(
    @SerialName("occurred_at") val occurredAt: String,
    @SerialName("app_version") val appVersion: String? = null,
    @SerialName("phone_battery_pct") val phoneBatteryPct: Int? = null,
    @SerialName("watch_bt_connected") val watchBtConnected: Boolean = false,
    /** Reported so the backend can show pipeline health instead of a mysterious
     *  silence when One UI has revoked something. */
    @SerialName("permissions_ok") val permissionsOk: Boolean = true,
)

@Serializable
data class IngestResultDto(
    val accepted: Int,
    val duplicates: Int,
    @SerialName("snapshot_updated") val snapshotUpdated: Boolean,
)

@Serializable
data class CommandDto(
    @SerialName("command_id") val commandId: String,
    @SerialName("subject_id") val subjectId: String,
    val type: String,
    val rung: Int,
    val params: JsonObject,
    @SerialName("issued_at") val issuedAt: String,
    @SerialName("expires_at") val expiresAt: String? = null,
    val signature: String,
    /** True for the rungs that seize the phone. Those are never executed from a
     *  push payload alone -- this response is the authority. */
    @SerialName("requires_validation") val requiresValidation: Boolean,
    @SerialName("checkin_id") val checkinId: String? = null,
)

@Serializable
data class CommandAckDto(
    val status: String,
    @SerialName("executed_at") val executedAt: String? = null,
    val detail: JsonObject? = null,
)

@Serializable
data class CommandResponseDto(
    val response: String,
    @SerialName("responded_at") val respondedAt: String,
    val source: String = "phone",
)

@Serializable
data class CheckinReportDto(
    val partial: Boolean,
    val result: JsonObject,
)
