package info.maurizioverde.accanto.collector.collect

import android.content.Context
import android.content.Intent
import android.util.Log
import info.maurizioverde.accanto.collector.data.AppGraph
import info.maurizioverde.accanto.collector.data.Mapping
import info.maurizioverde.accanto.collector.data.net.ApiResult
import info.maurizioverde.accanto.collector.data.net.CheckinReportDto
import info.maurizioverde.accanto.collector.data.net.CommandAckDto
import info.maurizioverde.accanto.collector.data.net.CommandDto
import info.maurizioverde.accanto.collector.data.net.CommandResponseDto
import info.maurizioverde.accanto.collector.domain.EventKind
import info.maurizioverde.accanto.collector.domain.HealthMapping
import info.maurizioverde.accanto.collector.domain.Source
import info.maurizioverde.accanto.collector.domain.Timestamps
import java.time.Instant
import kotlinx.coroutines.delay
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/**
 * Carries out what a caregiver asked for.
 *
 * The check-in is the interesting one. It does not order the watch to measure:
 * at a one-minute sampling interval the watch already has a fresh reading in its
 * buffer, and the delay is entirely in getting it across to the phone. So the
 * check-in forces that transfer, by opening Mi Fitness -- the only gateway there
 * is, since Vela exposes no API.
 *
 * The answer comes back in two parts on purpose. Phone-side signals are instant
 * and usually settle the question by themselves; the heart rate follows once the
 * sync completes. Making the caregiver wait for the slow half before seeing the
 * fast one would be a worse product for no reason.
 */
class CommandExecutor(
    private val context: Context,
    private val graph: AppGraph,
    private val signals: PhoneSignals,
    private val health: HealthConnectReader,
    private val onLiveLocation: (Boolean) -> Unit,
) {

    suspend fun execute(command: CommandDto) {
        Log.i(TAG, "executing ${command.type} (rung ${command.rung})")

        when (command.type) {
            "force_sync" -> forceSync(command)
            "location_live_on" -> { onLiveLocation(true); ack(command, "executed") }
            "location_live_off" -> { onLiveLocation(false); ack(command, "executed") }
            "vibrate" -> {
                Escalation.nudge(
                    context,
                    command.commandId,
                    message(command, "Tutto bene? Tocca per rispondere."),
                )
                ack(command, "executed")
            }
            "ring" -> {
                Escalation.ring(context)
                ack(command, "executed")
            }
            "confirm_prompt" -> {
                // Not acked here: the ack is the subject's answer, which arrives
                // through ConfirmActivity. Acking now would report the question
                // as resolved while nobody has answered it.
                Escalation.askForConfirmation(
                    context,
                    command.commandId,
                    message(command, "Tutto bene?"),
                )
            }
            "audio_out", "audio_channel" -> {
                // Not implemented, and deliberately not disguised. Sending a
                // rung-3 nudge instead made the loudest rung indistinguishable
                // from the quietest, and told the caregiver something had
                // happened that had not. An honest failure is more useful.
                ack(command, "failed", detail = "canale audio non ancora implementato")
            }
            else -> {
                Log.w(TAG, "unknown command type ${command.type}")
                ack(command, "failed", detail = "tipo di comando sconosciuto")
            }
        }
    }

    // ------------------------------------------------------------- force sync

    private suspend fun forceSync(command: CommandDto) {
        val subjectId = graph.pairing.subjectId ?: return

        // 1. Everything the phone already knows, sent immediately.
        val now = System.currentTimeMillis()
        graph.outbox.enqueueEvent(
            Mapping.toOutbox(subjectId, EventKind.HEARTBEAT, Source.PHONE, now, phoneState()),
        )
        graph.uploader.drain()
        report(command, partial = true, bpm = null)

        // 2. Open Mi Fitness so it pulls what the watch is holding. Background
        //    activity starts are blocked, but an app holding SYSTEM_ALERT_WINDOW
        //    is granted a documented exemption.
        val launched = launchMiFitness()
        if (!launched) {
            ack(command, "failed", detail = "Mi Fitness non disponibile")
            return
        }

        // 3. Wait for a sample newer than the request itself.
        val fresh = awaitFreshHeartRate(since = command.issuedAtMillis())
        if (fresh != null) {
            graph.outbox.enqueueEvent(
                Mapping.toOutbox(
                    subjectId,
                    EventKind.HR,
                    Source.WATCH,
                    fresh.epochMillis,
                    buildJsonObject { put("bpm", JsonPrimitive(fresh.bpm)) },
                ),
            )
            graph.uploader.drain()
        }

        report(command, partial = false, bpm = fresh?.bpm)
        ack(command, if (fresh != null) "executed" else "failed",
            detail = if (fresh == null) "nessun battito fresco entro il timeout" else null)
    }

    private fun launchMiFitness(): Boolean {
        val intent = context.packageManager.getLaunchIntentForPackage(MI_FITNESS)
            ?: return false
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        return runCatching { context.startActivity(intent); true }
            .getOrElse {
                Log.w(TAG, "could not launch Mi Fitness", it)
                false
            }
    }

    private suspend fun awaitFreshHeartRate(since: Long): HealthMapping.HeartRateSample? {
        if (!health.isAvailable || !health.hasPermissions()) return null

        val deadline = System.currentTimeMillis() + SYNC_TIMEOUT_MILLIS
        while (System.currentTimeMillis() < deadline) {
            delay(POLL_INTERVAL_MILLIS)
            val samples = health.heartRate(
                Instant.ofEpochMilli(since - FRESHNESS_GRACE_MILLIS),
                Instant.now(),
            )
            val newest = samples.maxByOrNull { it.epochMillis }
            if (newest != null && newest.epochMillis >= since - FRESHNESS_GRACE_MILLIS) return newest
        }
        return null
    }

    // ---------------------------------------------------------------- helpers

    private fun phoneState() = buildJsonObject {
        put("battery_pct", JsonPrimitive(signals.batteryPercent()))
        put("watch_bt_connected", JsonPrimitive(signals.watchConnected()))
        put("reason", JsonPrimitive("checkin"))
    }

    private suspend fun report(command: CommandDto, partial: Boolean, bpm: Int?) {
        val checkinId = command.checkinId ?: return
        val result = buildJsonObject {
            put("battery_pct", JsonPrimitive(signals.batteryPercent()))
            put("watch_bt_connected", JsonPrimitive(signals.watchConnected()))
            if (bpm != null) put("bpm", JsonPrimitive(bpm))
        }
        graph.api.reportCheckin(checkinId, CheckinReportDto(partial = partial, result = result))
    }

    private suspend fun ack(command: CommandDto, status: String, detail: String? = null) {
        val result = graph.api.ackCommand(
            command.commandId,
            CommandAckDto(
                status = status,
                executedAt = Timestamps.isoOffset(System.currentTimeMillis()),
                detail = detail?.let { buildJsonObject { put("detail", JsonPrimitive(it)) } },
            ),
        )
        if (result is ApiResult.Retryable) Log.i(TAG, "ack deferred: ${result.reason}")
    }

    suspend fun respondToPrompt(commandId: String, response: String) {
        graph.api.respondToCommand(
            commandId,
            CommandResponseDto(
                response = response,
                respondedAt = Timestamps.isoOffset(System.currentTimeMillis()),
            ),
        )
    }

    private fun message(command: CommandDto, fallback: String): String =
        (command.params["message"] as? kotlinx.serialization.json.JsonPrimitive)
            ?.content
            ?: fallback

    private fun CommandDto.issuedAtMillis(): Long =
        runCatching { java.time.OffsetDateTime.parse(issuedAt).toInstant().toEpochMilli() }
            .getOrDefault(System.currentTimeMillis())

    private companion object {
        const val TAG = "AccantoCommands"
        const val MI_FITNESS = "com.xiaomi.wearable"
        const val SYNC_TIMEOUT_MILLIS = 90_000L
        const val POLL_INTERVAL_MILLIS = 5_000L

        /** Mi Fitness may deliver a sample taken slightly before the request. */
        const val FRESHNESS_GRACE_MILLIS = 3 * 60_000L
    }
}
