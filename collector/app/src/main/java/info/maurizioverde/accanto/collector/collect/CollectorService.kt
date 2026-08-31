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

    private var liveModeSince: Long? = null

    override fun onCreate() {
        super.onCreate()
        graph = AppGraph.of(this)

        signals = PhoneSignals(this) { kind, at -> record(kind, Source.PHONE, at) }
        location = LocationSource(this, ::onFix)
        activity = ActivitySource(this, ::onMovement)
        usage = UsageSource(this)
        health = HealthConnectReader(this)

        signals.start()
        location.start(LocationMode.IDLE)
        activity.start()

        startForegroundWithType()

        scope.launch { uploadLoop() }
        scope.launch { heartbeatLoop() }
        scope.launch { healthLoop() }
        scope.launch { catchUpOnMissedUsage() }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_LIVE_LOCATION_ON -> enableLiveLocation()
            ACTION_LIVE_LOCATION_OFF -> disableLiveLocation()
        }
        // Restart if the system kills us: an unattended collector that stays
        // down is worse than one that costs a little battery.
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        signals.stop()
        location.stop()
        activity.stop()
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
        val since = maxOf(
            graph.pairing.lastHealthReadMillis,
            now - HealthConnectReader.MAX_LOOKBACK_MILLIS,
        )
        if (now <= since) return

        val from = Instant.ofEpochMilli(since)
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

        graph.pairing.lastHealthReadMillis = now
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

    private fun startForegroundWithType() {
        val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            ServiceInfo.FOREGROUND_SERVICE_TYPE_HEALTH
        } else {
            0
        }
        ServiceCompat.startForeground(this, NOTIFICATION_ID, buildNotification(null), type)
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

        const val ACTION_LIVE_LOCATION_ON = "info.maurizioverde.accanto.LIVE_ON"
        const val ACTION_LIVE_LOCATION_OFF = "info.maurizioverde.accanto.LIVE_OFF"

        fun start(context: Context) {
            context.startForegroundService(Intent(context, CollectorService::class.java))
        }

        fun setLiveLocation(context: Context, enabled: Boolean) {
            val intent = Intent(context, CollectorService::class.java).setAction(
                if (enabled) ACTION_LIVE_LOCATION_ON else ACTION_LIVE_LOCATION_OFF,
            )
            context.startForegroundService(intent)
        }
    }
}
