package info.maurizioverde.accanto.collector.collect

import android.app.Notification
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import info.maurizioverde.accanto.collector.AccantoApplication
import info.maurizioverde.accanto.collector.BuildConfig
import info.maurizioverde.accanto.collector.R
import info.maurizioverde.accanto.collector.data.AppGraph
import info.maurizioverde.accanto.collector.data.Mapping
import info.maurizioverde.accanto.collector.data.net.HeartbeatDto
import info.maurizioverde.accanto.collector.domain.Debouncer
import info.maurizioverde.accanto.collector.domain.EventKind
import info.maurizioverde.accanto.collector.domain.Geo
import info.maurizioverde.accanto.collector.domain.HealthMapping
import info.maurizioverde.accanto.collector.domain.LocationMode
import info.maurizioverde.accanto.collector.domain.LocationPolicy
import info.maurizioverde.accanto.collector.domain.Movement
import info.maurizioverde.accanto.collector.domain.MovementKind
import info.maurizioverde.accanto.collector.domain.Source
import info.maurizioverde.accanto.collector.domain.Timestamps
import info.maurizioverde.accanto.collector.ui.MainActivity
import java.time.Instant
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/**
 * The heart of the collector.
 *
 * A foreground service is not a stylistic choice: without one, One UI suspends
 * the process and the pipeline stops with no error raised anywhere. That failure
 * would look, from the caregiver's side, exactly like the situation the product
 * exists to detect.
 *
 * In steady state this costs very little. Broadcasts are free, activity
 * recognition runs in a co-processor, GPS is coarse and infrequent, and nothing
 * is polled tightly. The expensive work -- a forced sync, precise GPS -- happens
 * only when a caregiver asks for it.
 */
class CollectorService : Service() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val debouncer = Debouncer()

    private lateinit var graph: AppGraph
    private lateinit var signals: PhoneSignals
    private lateinit var location: LocationSource
    private lateinit var activity: ActivitySource
    private lateinit var usage: UsageSource
    private lateinit var health: HealthConnectReader
    private lateinit var executor: CommandExecutor
    private var call: AudioCall? = null
    private var activeSession: String? = null

    private var liveModeSince: Long? = null

    /** False when onCreate bailed out; onDestroy must not touch uninitialised sources. */
    private var started = false

    /** Commands currently executing, so a poll does not start one twice. */
    private val inFlight = java.util.Collections.synchronizedSet(mutableSetOf<String>())

    /**
     * Commands already carried out on this device.
     *
     * The backend is the record of truth, but an acknowledgement can fail while
     * the action itself succeeded. Without this, the command stays pending
     * server-side and every poll runs it again -- which for a rung-3 nudge means
     * buzzing the subject every ten seconds indefinitely. Being pestered by the
     * app is a faster route to it being uninstalled than any missing feature.
     */
    private val alreadyExecuted = java.util.Collections.synchronizedSet(mutableSetOf<String>())

    override fun onCreate() {
        super.onCreate()
        graph = AppGraph.of(this)

        val permissions = Permissions.inspect(this)

        // Going foreground is the very first thing: the platform kills a service
        // that has not called startForeground promptly. If it is refused there
        // is nothing useful this service can do, so it stops cleanly and the
        // dashboard tells the subject what is missing.
        if (!startForegroundWithType(permissions)) {
            Log.w(TAG, "cannot run without permissions: ${permissions.missing}")
            stopSelf()
            return
        }

        signals = PhoneSignals(this) { kind, at -> record(kind, Source.PHONE, at) }
        location = LocationSource(this, ::onFix)
        activity = ActivitySource(this, ::onMovement)
        usage = UsageSource(this)
        health = HealthConnectReader(this)

        signals.start()
        location.start(LocationMode.IDLE)
        activity.start()
        started = true

        executor = CommandExecutor(
            this,
            graph,
            signals,
            health,
            onLiveLocation = { enabled -> if (enabled) enableLiveLocation() else disableLiveLocation() },
            onAudioChannel = { sessionId -> startAudioCall(sessionId) },
        )

        scope.launch { uploadLoop() }
        scope.launch { heartbeatLoop() }
        scope.launch { healthLoop() }
        scope.launch { commandLoop() }
        scope.launch { catchUpOnMissedUsage() }
        scope.launch { runCatching { health.survey() } }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (!started) return START_NOT_STICKY
        when (intent?.action) {
            ACTION_LIVE_LOCATION_ON -> enableLiveLocation()
            ACTION_LIVE_LOCATION_OFF -> disableLiveLocation()
            ACTION_END_AUDIO -> endAudioCall("subject")
            ACTION_PROMPT_RESPONSE -> {
                val commandId = intent.getStringExtra(EXTRA_COMMAND_ID)
                val response = intent.getStringExtra(EXTRA_RESPONSE)
                if (commandId != null && response != null) {
                    scope.launch { executor.respondToPrompt(commandId, response) }
                }
            }
        }
        // Restart if the system kills us: an unattended collector that stays
        // down is worse than one that costs a little battery.
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        if (started) {
            signals.stop()
            location.stop()
            activity.stop()
        }
        scope.cancel()
        super.onDestroy()
    }

    // ------------------------------------------------------------------ signals

    private fun record(
        kind: EventKind,
        source: Source,
        atMillis: Long,
        payload: kotlinx.serialization.json.JsonObject = buildJsonObject { },
    ) {
        val subjectId = graph.pairing.subjectId ?: return
        if (!debouncer.accept(kind, source, atMillis)) return

        // A phone whose clock is badly wrong would otherwise queue events the
        // backend refuses, and they would sit at the head of the queue forever.
        if (Timestamps.isImplausiblyFuture(atMillis, System.currentTimeMillis())) {
            Log.w(TAG, "dropping $kind: device clock is implausibly ahead")
            return
        }

        scope.launch {
            graph.outbox.enqueueEvent(Mapping.toOutbox(subjectId, kind, source, atMillis, payload))
        }
    }

    private fun onFix(fix: Geo.Fix, movementEvidence: Boolean) {
        val subjectId = graph.pairing.subjectId ?: return

        scope.launch {
            graph.outbox.enqueueLocation(
                Mapping.toOutboxLocation(
                    subjectId = subjectId,
                    occurredAtMillis = fix.epochMillis,
                    lat = fix.lat,
                    lon = fix.lon,
                    accuracyM = fix.accuracyM,
                    speedMps = null,
                    batteryPct = signals.batteryPercent(),
                ),
            )
        }

        // A new position is always worth recording; only a real displacement is
        // evidence that the person is moving.
        if (movementEvidence) record(EventKind.LOCATION_MOVE, Source.PHONE, fix.epochMillis)
    }

    private fun onMovement(kind: MovementKind, confidence: Int, atMillis: Long) {
        record(
            EventKind.ACTIVITY,
            Source.PHONE,
            atMillis,
            buildJsonObject {
                put("activity", JsonPrimitive(kind.name))
                put("label", JsonPrimitive(Movement.label(kind)))
                put("confidence", JsonPrimitive(confidence))
            },
        )
    }

    // -------------------------------------------------------------------- loops

    private suspend fun uploadLoop() {
        while (scope.isActive) {
            if (graph.pairing.isPaired) {
                runCatching {
                    graph.uploader.trimIfHuge()
                    graph.uploader.drain()
                }.onFailure { Log.w(TAG, "upload pass failed", it) }
                graph.uploader.awaitBackoff()
            }
            expireLiveLocationIfStale()
            delay(UPLOAD_INTERVAL_MILLIS)
        }
    }

    private suspend fun heartbeatLoop() {
        while (scope.isActive) {
            if (graph.pairing.isPaired) {
                val permissions = Permissions.inspect(this)
                val now = System.currentTimeMillis()

                runCatching {
                    graph.api.sendHeartbeat(
                        HeartbeatDto(
                            occurredAt = Timestamps.isoOffset(now),
                            appVersion = BuildConfig.VERSION_NAME,
                            phoneBatteryPct = signals.batteryPercent(),
                            watchBtConnected = signals.watchConnected(),
                            permissionsOk = permissions.allGranted,
                        ),
                    )
                }.onFailure { Log.w(TAG, "heartbeat failed", it) }

                updateNotification(permissions)
            }
            delay(HEARTBEAT_INTERVAL_MILLIS)
        }
    }

    /**
     * Pulls what the watch has deposited in Health Connect.
     *
     * Polled rather than pushed: Health Connect offers no callback for new
     * records, so a moderate cadence is the honest option. It is also why the
     * heart rate is minutes behind while everything from the phone is immediate.
     */
    private suspend fun healthLoop() {
        while (scope.isActive) {
            val subjectId = graph.pairing.subjectId
            if (subjectId != null && health.isAvailable && health.hasPermissions()) {
                runCatching { readHealth(subjectId) }
                    .onFailure { Log.w(TAG, "health read failed", it) }
            }
            delay(HEALTH_INTERVAL_MILLIS)
        }
    }

    private suspend fun readHealth(subjectId: String) {
        val now = System.currentTimeMillis()

        // Always re-scan a wide window, never "since the last read".
        //
        // Health Connect receives this data retroactively: Mi Fitness syncs
        // with the watch and inserts samples carrying their original
        // timestamps, often minutes old. A watermark on sample time therefore
        // misses everything that arrives late -- which, with this sync model,
        // is all of it. With the watch sampling every ten minutes and the poll
        // running every three, the window never once contained a reading.
        //
        // Re-reading is free: ingest is idempotent on the dedup key, so a
        // sample already sent is recognised and discarded server-side.
        val from = Instant.ofEpochMilli(now - HealthConnectReader.MAX_LOOKBACK_MILLIS)
        val to = Instant.ofEpochMilli(now)

        for (sample in health.heartRate(from, to)) {
            graph.outbox.enqueueEvent(
                Mapping.toOutbox(
                    subjectId = subjectId,
                    kind = EventKind.HR,
                    source = Source.WATCH,
                    occurredAtMillis = sample.epochMillis,
                    payload = buildJsonObject { put("bpm", JsonPrimitive(sample.bpm)) },
                ),
            )
        }

        for (bucket in health.steps(from, to)) {
            graph.outbox.enqueueEvent(
                Mapping.toOutbox(
                    subjectId = subjectId,
                    kind = EventKind.STEPS,
                    source = Source.WATCH,
                    occurredAtMillis = HealthMapping.attributedInstant(bucket),
                    payload = buildJsonObject { put("count", JsonPrimitive(bucket.count)) },
                ),
            )
        }

        // Recorded for diagnostics only; the window no longer depends on it.
        graph.pairing.lastHealthReadMillis = now
    }

    /**
     * Picks up what the caregiver has asked for.
     *
     * Polled rather than pushed. FCM is the intended transport, but push
     * delivery is best effort and a caregiving system cannot rest on it: the one
     * moment it fails is the moment somebody wanted an answer. Polling is the
     * floor beneath the push, and it is also what makes the system work with no
     * Firebase project at all.
     */
    private suspend fun commandLoop() {
        while (scope.isActive) {
            if (graph.pairing.isPaired) {
                when (val pending = graph.api.pendingCommands()) {
                    is info.maurizioverde.accanto.collector.data.net.ApiResult.Ok ->
                        for (command in pending.value) dispatch(command)
                    else -> Unit
                }
            }
            delay(COMMAND_POLL_MILLIS)
        }
    }

    /**
     * Runs each command on its own coroutine.
     *
     * A forced sync waits up to ninety seconds for the watch to deliver a fresh
     * reading. Executed in sequence, that made a discreet nudge queue behind it
     * -- so the quietest rung on the ladder became the slowest, which is exactly
     * backwards. `inFlight` stops the poll from starting the same command again
     * while it is still running.
     */
    private fun dispatch(command: info.maurizioverde.accanto.collector.data.net.CommandDto) {
        // Two separate guards, for two separate failures. `inFlight` stops a
        // poll from starting a command that is still running; `alreadyExecuted`
        // stops one from running again after an acknowledgement failed to
        // reach the server. The second cost a real person a notification every
        // ten seconds before it existed.
        if (command.commandId in alreadyExecuted) return
        if (!inFlight.add(command.commandId)) return

        scope.launch {
            try {
                executor.execute(command)
                alreadyExecuted.add(command.commandId)
            } catch (error: Exception) {
                Log.w(TAG, "command ${command.type} failed", error)
                // Also remembered on failure. A command that threw halfway may
                // already have buzzed the phone, and repeating it is worse than
                // skipping it: the caregiver can always ask again.
                alreadyExecuted.add(command.commandId)
            } finally {
                inFlight.remove(command.commandId)
                trimExecutedHistory()
            }
        }
    }

    /** Commands expire server-side, so this set never needs to grow without bound. */
    private fun trimExecutedHistory() {
        if (alreadyExecuted.size <= MAX_REMEMBERED_COMMANDS) return
        synchronized(alreadyExecuted) {
            val excess = alreadyExecuted.size - MAX_REMEMBERED_COMMANDS
            alreadyExecuted.take(excess).forEach { alreadyExecuted.remove(it) }
        }
    }

    /**
     * Recovers the interaction the unlock broadcast could not see.
     *
     * After a reboot or a crash the service was not listening, and that gap
     * would read as silence -- the very thing the caregiver is asked to worry
     * about. Usage stats fill it in retroactively.
     */
    private suspend fun catchUpOnMissedUsage() {
        val now = System.currentTimeMillis()
        val lastUse = usage.lastForegroundUseMillis(now - USAGE_LOOKBACK_MILLIS, now) ?: return
        record(EventKind.APP_USAGE, Source.PHONE, lastUse)
    }

    // -------------------------------------------------------------- audio call

    private suspend fun startAudioCall(sessionId: String): Boolean {
        endAudioCall("subject")

        // The microphone needs its own foreground-service type. Adding it only
        // for the duration of a call means the service does not hold a
        // microphone claim while merely watching for steps.
        if (!promoteToMicrophone()) return false

        val session = AudioCall(this, scope, AudioBridge(graph))
        call = session
        activeSession = sessionId

        val started = session.start(sessionId)
        if (started) {
            showCallNotification()
        } else {
            endAudioCall("subject")
        }
        return started
    }

    fun endAudioCall(by: String) {
        val session = call ?: return
        val id = activeSession
        call = null
        activeSession = null
        scope.launch { session.stop(id, by) }
        getSystemService(NotificationManager::class.java)?.cancel(CALL_NOTIFICATION_ID)
        runCatching { startForegroundWithType(Permissions.inspect(this)) }
    }

    private fun promoteToMicrophone(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.UPSIDE_DOWN_CAKE) return true
        val permissions = Permissions.inspect(this)
        var type = ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
        if (permissions.activityRecognition) type = type or ServiceInfo.FOREGROUND_SERVICE_TYPE_HEALTH
        if (permissions.fineLocation) type = type or ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION

        return try {
            ServiceCompat.startForeground(
                this, NOTIFICATION_ID, buildNotification(permissions), type,
            )
            true
        } catch (error: SecurityException) {
            // Android restricts starting a microphone foreground service from
            // the background. Refused means no call, and the caregiver is told
            // so rather than left waiting for audio that never arrives.
            Log.w(TAG, "microfono rifiutato dalla piattaforma", error)
            false
        }
    }

    /** A persistent, unmissable notification for as long as the mic is open. */
    private fun showCallNotification() {
        val hangUp = PendingIntent.getService(
            this,
            0,
            Intent(this, CollectorService::class.java).setAction(ACTION_END_AUDIO),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val notification = NotificationCompat.Builder(this, AccantoApplication.CHANNEL_ALARM)
            .setContentTitle(getString(R.string.call_active_title))
            .setContentText(getString(R.string.call_active_text))
            .setSmallIcon(R.drawable.ic_notification)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_CALL)
            .addAction(R.drawable.ic_notification, getString(R.string.call_end), hangUp)
            .build()
        getSystemService(NotificationManager::class.java)?.notify(CALL_NOTIFICATION_ID, notification)
    }

    // ------------------------------------------------------------- live location

    private fun enableLiveLocation() {
        liveModeSince = System.currentTimeMillis()
        location.setMode(LocationMode.LIVE)
        Log.i(TAG, "live location on")
    }

    private fun disableLiveLocation() {
        liveModeSince = null
        location.setMode(LocationMode.IDLE)
        Log.i(TAG, "live location off")
    }

    /**
     * Live mode expires by itself. If the caregiver closed the tab without a
     * clean disconnect, the phone must not keep burning GPS until it is flat.
     */
    private fun expireLiveLocationIfStale() {
        val since = liveModeSince ?: return
        if (LocationPolicy.liveModeExpired(since, System.currentTimeMillis())) {
            disableLiveLocation()
        }
    }

    // ------------------------------------------------------------- notification

    /**
     * Starts in the foreground with only the types this app may currently use.
     *
     * Android 14+ validates each declared type against a runtime permission that
     * backs it: `health` needs activity recognition or a health read permission,
     * `location` needs a location permission. Claiming a type without its
     * backing permission throws a SecurityException and kills the process.
     *
     * Returns false if the service cannot legally run, so the caller stops
     * rather than the platform killing us.
     */
    private fun startForegroundWithType(permissions: PermissionState): Boolean {
        var type = 0
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            if (permissions.activityRecognition) {
                type = type or ServiceInfo.FOREGROUND_SERVICE_TYPE_HEALTH
            }
            if (permissions.fineLocation) {
                type = type or ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION
            }
            if (type == 0) return false
        }

        return try {
            ServiceCompat.startForeground(this, NOTIFICATION_ID, buildNotification(permissions), type)
            true
        } catch (error: SecurityException) {
            // Belt and braces: a permission revoked between the check and this
            // call must degrade, never crash. The subject sees the app is broken
            // in the dashboard; a crash loop would tell them nothing.
            Log.e(TAG, "foreground service refused by the platform", error)
            false
        }
    }

    private fun updateNotification(permissions: PermissionState) {
        getSystemService(NotificationManager::class.java)
            ?.notify(NOTIFICATION_ID, buildNotification(permissions))
    }

    private fun buildNotification(permissions: PermissionState?): Notification {
        val open = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE,
        )

        // The subject sees this permanently. It says plainly what is running, and
        // speaks up when a revoked permission has broken things -- that is the
        // moment they can actually fix it.
        val text = when {
            permissions == null || permissions.allGranted -> getString(R.string.service_running)
            else -> getString(R.string.service_degraded, permissions.missing.joinToString(", "))
        }

        return NotificationCompat.Builder(this, AccantoApplication.CHANNEL_SERVICE)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(text)
            .setSmallIcon(R.drawable.ic_notification)
            .setOngoing(true)
            .setSilent(true)
            .setContentIntent(open)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }

    companion object {
        private const val TAG = "AccantoService"
        private const val NOTIFICATION_ID = 1001
        private const val UPLOAD_INTERVAL_MILLIS = 60_000L
        private const val HEARTBEAT_INTERVAL_MILLIS = 5 * 60_000L
        private const val HEALTH_INTERVAL_MILLIS = 3 * 60_000L
        private const val USAGE_LOOKBACK_MILLIS = 12 * 60 * 60_000L

        /** Short: this is the latency a caregiver feels when they press the button. */
        private const val COMMAND_POLL_MILLIS = 10_000L
        private const val MAX_REMEMBERED_COMMANDS = 200

        const val ACTION_LIVE_LOCATION_ON = "info.maurizioverde.accanto.LIVE_ON"
        const val ACTION_LIVE_LOCATION_OFF = "info.maurizioverde.accanto.LIVE_OFF"
        const val ACTION_PROMPT_RESPONSE = "info.maurizioverde.accanto.PROMPT_RESPONSE"
        const val ACTION_END_AUDIO = "info.maurizioverde.accanto.END_AUDIO"
        private const val CALL_NOTIFICATION_ID = 1002
        const val EXTRA_COMMAND_ID = "command_id"
        const val EXTRA_RESPONSE = "response"

        fun start(context: Context) {
            context.startForegroundService(Intent(context, CollectorService::class.java))
        }

        /** Called by the full-screen prompt when the subject answers. */
        fun respondToPrompt(context: Context, commandId: String, response: String) {
            val intent = Intent(context, CollectorService::class.java)
                .setAction(ACTION_PROMPT_RESPONSE)
                .putExtra(EXTRA_COMMAND_ID, commandId)
                .putExtra(EXTRA_RESPONSE, response)
            context.startForegroundService(intent)
        }

        fun setLiveLocation(context: Context, enabled: Boolean) {
            val intent = Intent(context, CollectorService::class.java).setAction(
                if (enabled) ACTION_LIVE_LOCATION_ON else ACTION_LIVE_LOCATION_OFF,
            )
            context.startForegroundService(intent)
        }
    }
}
