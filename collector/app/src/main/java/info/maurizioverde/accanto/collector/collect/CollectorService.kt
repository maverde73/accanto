package info.maurizioverde.accanto.collector.collect

import android.app.Notification
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
import info.maurizioverde.accanto.collector.domain.Source
import info.maurizioverde.accanto.collector.domain.Timestamps
import info.maurizioverde.accanto.collector.ui.MainActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * The heart of the collector.
 *
 * A foreground service is not a stylistic choice: without one, One UI suspends
 * the process and the pipeline stops with no error raised anywhere. That failure
 * would look, from the caregiver's side, exactly like the situation the product
 * exists to detect.
 *
 * In steady state this costs very little. Broadcasts are free, the heartbeat is
 * infrequent, and nothing is polled. The expensive work -- a forced sync, precise
 * GPS -- happens only when a caregiver asks for it.
 */
class CollectorService : Service() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val debouncer = Debouncer()

    private lateinit var signals: PhoneSignals
    private lateinit var graph: AppGraph

    override fun onCreate() {
        super.onCreate()
        graph = AppGraph.of(this)

        signals = PhoneSignals(this) { kind, at -> record(kind, Source.PHONE, at) }
        signals.start()

        startForegroundWithType()
        scope.launch { uploadLoop() }
        scope.launch { heartbeatLoop() }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // Restart if the system kills us: an unattended collector that stays
        // down is worse than one that costs a little battery.
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        signals.stop()
        scope.cancel()
        super.onDestroy()
    }

    // ------------------------------------------------------------------ signals

    private fun record(kind: EventKind, source: Source, atMillis: Long) {
        val subjectId = graph.pairing.subjectId ?: return
        if (!debouncer.accept(kind, source, atMillis)) return

        // A phone whose clock is badly wrong would otherwise queue events the
        // backend refuses, and they would sit at the head of the queue forever.
        if (Timestamps.isImplausiblyFuture(atMillis, System.currentTimeMillis())) {
            Log.w(TAG, "dropping $kind: device clock is implausibly ahead")
            return
        }

        scope.launch {
            graph.outbox.enqueueEvent(Mapping.toOutbox(subjectId, kind, source, atMillis))
        }
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
        val manager = getSystemService(NotificationManager::class.java)
        manager?.notify(NOTIFICATION_ID, buildNotification(permissions))
    }

    private fun buildNotification(permissions: PermissionState?): Notification {
        val open = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE,
        )

        // The subject sees this notification permanently. It says plainly what is
        // running, and speaks up when a revoked permission has broken things --
        // that is the moment they can actually fix it.
        val text = when {
            permissions == null -> getString(R.string.service_running)
            permissions.allGranted -> getString(R.string.service_running)
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

        fun start(context: Context) {
            val intent = Intent(context, CollectorService::class.java)
            context.startForegroundService(intent)
        }
    }
}

private typealias NotificationManager = android.app.NotificationManager
