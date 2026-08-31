package info.maurizioverde.accanto.collector.collect

import android.Manifest
import android.app.AppOpsManager
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.PowerManager
import android.provider.Settings
import androidx.core.content.ContextCompat

/**
 * What the collector is currently allowed to do.
 *
 * This is not a setup convenience: One UI, or an OS update, can revoke a
 * permission months later and the pipeline then goes quiet with no error
 * anywhere. Without this check the failure looks exactly like the thing the
 * whole product is meant to detect -- a person who has gone silent.
 *
 * The result rides along with every heartbeat, so the backend can show it as
 * pipeline health rather than as an alarm about someone.
 */
data class PermissionState(
    val fineLocation: Boolean,
    val backgroundLocation: Boolean,
    val activityRecognition: Boolean,
    val notifications: Boolean,
    val bluetooth: Boolean,
    val usageStats: Boolean,
    val overlay: Boolean,
    val batteryUnrestricted: Boolean,
) {
    /** Everything the collector needs to keep reporting without help. */
    val allGranted: Boolean
        get() = fineLocation && backgroundLocation && activityRecognition &&
            notifications && bluetooth && usageStats && overlay && batteryUnrestricted

    /**
     * Whether the foreground service can legally start.
     *
     * Android 14+ refuses a `health` foreground service unless the app already
     * holds a runtime permission that backs it, and refuses `location` likewise.
     * Declaring them in the manifest is not enough. Starting anyway throws a
     * SecurityException and kills the process -- which, before this check
     * existed, happened the instant a user finished pairing.
     */
    val canRunService: Boolean
        get() = activityRecognition || fineLocation

    val missing: List<String>
        get() = buildList {
            if (!fineLocation) add("posizione")
            if (!backgroundLocation) add("posizione sempre")
            if (!activityRecognition) add("attività fisica")
            if (!notifications) add("notifiche")
            if (!bluetooth) add("dispositivi vicini")
            if (!usageStats) add("accesso all'uso")
            if (!overlay) add("sopra altre app")
            if (!batteryUnrestricted) add("batteria senza restrizioni")
        }
}

object Permissions {

    fun inspect(context: Context): PermissionState = PermissionState(
        fineLocation = granted(context, Manifest.permission.ACCESS_FINE_LOCATION),
        backgroundLocation = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            granted(context, Manifest.permission.ACCESS_BACKGROUND_LOCATION)
        } else {
            true
        },
        activityRecognition = granted(context, Manifest.permission.ACTIVITY_RECOGNITION),
        notifications = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            granted(context, Manifest.permission.POST_NOTIFICATIONS)
        } else {
            true
        },
        bluetooth = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            granted(context, Manifest.permission.BLUETOOTH_CONNECT)
        } else {
            true
        },
        usageStats = hasUsageStats(context),
        overlay = Settings.canDrawOverlays(context),
        batteryUnrestricted = ignoresBatteryOptimisations(context),
    )

    private fun granted(context: Context, permission: String): Boolean =
        ContextCompat.checkSelfPermission(context, permission) == PackageManager.PERMISSION_GRANTED

    /** Special access, granted from a Settings screen rather than a dialog. */
    private fun hasUsageStats(context: Context): Boolean {
        val ops = context.getSystemService(Context.APP_OPS_SERVICE) as? AppOpsManager ?: return false
        val mode = ops.unsafeCheckOpNoThrow(
            AppOpsManager.OPSTR_GET_USAGE_STATS,
            android.os.Process.myUid(),
            context.packageName,
        )
        return mode == AppOpsManager.MODE_ALLOWED
    }

    /**
     * Battery set to "unrestricted". Without it One UI suspends the app and the
     * data simply stops, which is the most common cause of a silent system.
     */
    private fun ignoresBatteryOptimisations(context: Context): Boolean {
        val power = context.getSystemService(Context.POWER_SERVICE) as? PowerManager ?: return false
        return power.isIgnoringBatteryOptimizations(context.packageName)
    }
}
