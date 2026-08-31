package info.maurizioverde.accanto.collector.collect

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.os.Looper
import android.util.Log
import androidx.core.content.ContextCompat
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import info.maurizioverde.accanto.collector.domain.Geo
import info.maurizioverde.accanto.collector.domain.LocationMode
import info.maurizioverde.accanto.collector.domain.LocationPolicy

/**
 * Position, from the phone rather than the watch.
 *
 * The Redmi Watch exposes no live GPS -- only a workout track, after the fact.
 * The phone is with the person anyway, so it gives the same answer, sooner and
 * more precisely.
 *
 * Two regimes: cheap by default, precise only while someone is watching.
 */
class LocationSource(
    private val context: Context,
    private val onFix: (Geo.Fix, movementEvidence: Boolean) -> Unit,
) {

    private val client = LocationServices.getFusedLocationProviderClient(context)
    private var callback: LocationCallback? = null
    private var lastStored: Geo.Fix? = null
    private var mode: LocationMode = LocationMode.IDLE

    val currentMode: LocationMode get() = mode

    fun start(mode: LocationMode = LocationMode.IDLE) {
        if (!hasPermission()) {
            Log.i(TAG, "location permission missing; source not started")
            return
        }
        this.mode = mode
        restart()
    }

    /** Switches regime without losing the last fix used for comparison. */
    fun setMode(mode: LocationMode) {
        if (this.mode == mode) return
        this.mode = mode
        if (callback != null) restart()
    }

    fun stop() {
        callback?.let { client.removeLocationUpdates(it) }
        callback = null
    }

    @SuppressLint("MissingPermission")
    private fun restart() {
        stop()
        val spec = LocationPolicy.specFor(mode)
        val priority = if (spec.highAccuracy) {
            Priority.PRIORITY_HIGH_ACCURACY
        } else {
            Priority.PRIORITY_BALANCED_POWER_ACCURACY
        }

        val request = LocationRequest.Builder(priority, spec.intervalMillis)
            .setMinUpdateDistanceMeters(spec.minUpdateDistanceMeters)
            .setWaitForAccurateLocation(false)
            .build()

        val listener = object : LocationCallback() {
            override fun onLocationResult(result: LocationResult) {
                val location = result.lastLocation ?: return
                val fix = Geo.Fix(
                    epochMillis = location.time,
                    lat = location.latitude,
                    lon = location.longitude,
                    accuracyM = if (location.hasAccuracy()) location.accuracy else null,
                )

                // Drift while the phone lies on a table is not a journey.
                if (!Geo.shouldStore(lastStored, fix)) return

                val moved = Geo.isMovementEvidence(lastStored, fix)
                lastStored = fix
                onFix(fix, moved)
            }
        }

        callback = listener
        runCatching {
            client.requestLocationUpdates(request, listener, Looper.getMainLooper())
        }.onFailure { Log.w(TAG, "could not request location updates", it) }
    }

    private fun hasPermission(): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED

    private companion object {
        const val TAG = "AccantoLocation"
    }
}
