package info.maurizioverde.accanto.collector.collect

import android.Manifest
import android.annotation.SuppressLint
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.util.Log
import androidx.core.content.ContextCompat
import com.google.android.gms.location.ActivityRecognition
import com.google.android.gms.location.ActivityRecognitionResult
import com.google.android.gms.location.DetectedActivity
import info.maurizioverde.accanto.collector.domain.Movement
import info.maurizioverde.accanto.collector.domain.MovementKind

/**
 * What the person is doing, from the phone's hardware classifier.
 *
 * Cheap: the work happens in a co-processor, not in our process. Reports
 * transitions rather than being polled, which is why the steady-state cost of
 * the whole collector stays near zero.
 */
class ActivitySource(
    private val context: Context,
    private val onMovement: (MovementKind, Int, Long) -> Unit,
) {

    private var receiver: BroadcastReceiver? = null
    private var pending: PendingIntent? = null

    @SuppressLint("MissingPermission")
    fun start() {
        if (receiver != null) return
        if (!hasPermission()) {
            Log.i(TAG, "activity recognition permission missing; source not started")
            return
        }

        receiver = object : BroadcastReceiver() {
            override fun onReceive(ctx: Context?, intent: Intent?) {
                val result = intent?.let { ActivityRecognitionResult.extractResult(it) } ?: return
                val probable = result.mostProbableActivity
                val kind = toKind(probable.type)

                if (!Movement.isEvidence(kind, probable.confidence)) return
                onMovement(kind, probable.confidence, System.currentTimeMillis())
            }
        }
        context.registerReceiver(receiver, IntentFilter(ACTION), Context.RECEIVER_NOT_EXPORTED)

        val intent = Intent(ACTION).setPackage(context.packageName)
        pending = PendingIntent.getBroadcast(
            context,
            0,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE,
        )

        runCatching {
            ActivityRecognition.getClient(context)
                .requestActivityUpdates(DETECTION_INTERVAL_MILLIS, pending!!)
        }.onFailure { Log.w(TAG, "could not request activity updates", it) }
    }

    fun stop() {
        pending?.let {
            runCatching { ActivityRecognition.getClient(context).removeActivityUpdates(it) }
        }
        receiver?.let { runCatching { context.unregisterReceiver(it) } }
        receiver = null
        pending = null
    }

    private fun hasPermission(): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.ACTIVITY_RECOGNITION) ==
            PackageManager.PERMISSION_GRANTED

    private fun toKind(type: Int): MovementKind = when (type) {
        DetectedActivity.WALKING, DetectedActivity.ON_FOOT -> MovementKind.WALKING
        DetectedActivity.RUNNING -> MovementKind.RUNNING
        DetectedActivity.ON_BICYCLE -> MovementKind.ON_BICYCLE
        DetectedActivity.IN_VEHICLE -> MovementKind.IN_VEHICLE
        DetectedActivity.STILL -> MovementKind.STILL
        else -> MovementKind.UNKNOWN
    }

    private companion object {
        const val TAG = "AccantoActivity"
        const val ACTION = "info.maurizioverde.accanto.collector.ACTIVITY_UPDATE"
        const val DETECTION_INTERVAL_MILLIS = 2 * 60_000L
    }
}
