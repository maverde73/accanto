package info.maurizioverde.accanto.collector.collect

import android.app.usage.UsageStatsManager
import android.content.Context
import android.util.Log

/**
 * When the phone was last actually used.
 *
 * The strongest liveness signal in the system, and nearly free. "She used her
 * phone four minutes ago" settles the question better than any heart rate: a
 * normal BPM is equally consistent with someone asleep or unconscious, while
 * picking up a phone takes intent.
 *
 * The unlock broadcast covers the live case, but only while the service is
 * running. This fills the gap after a reboot or a crash, when the app needs to
 * know what it missed.
 */
class UsageSource(private val context: Context) {

    /**
     * Most recent foreground app use in the window, or null if the permission
     * is missing or nothing was used.
     */
    fun lastForegroundUseMillis(sinceMillis: Long, nowMillis: Long): Long? {
        val manager = context.getSystemService(Context.USAGE_STATS_SERVICE) as? UsageStatsManager
            ?: return null

        return runCatching {
            manager.queryUsageStats(UsageStatsManager.INTERVAL_DAILY, sinceMillis, nowMillis)
                ?.asSequence()
                ?.filter { it.lastTimeUsed in (sinceMillis + 1)..nowMillis }
                // Ignore our own foreground service: the collector using itself
                // is not the person using the phone.
                ?.filterNot { it.packageName == context.packageName }
                ?.maxOfOrNull { it.lastTimeUsed }
        }.getOrElse {
            // Thrown when "usage access" was never granted or has been revoked.
            Log.i(TAG, "usage stats unavailable: ${it.message}")
            null
        }
    }

    private companion object {
        const val TAG = "AccantoUsage"
    }
}
