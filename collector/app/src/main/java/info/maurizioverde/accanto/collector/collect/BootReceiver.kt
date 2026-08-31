package info.maurizioverde.accanto.collector.collect

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import info.maurizioverde.accanto.collector.data.AppGraph

/**
 * Restarts the collector after a reboot.
 *
 * Samsung's Device Care can restart the phone overnight. Without this the
 * service would stay down until someone opened the app -- and the caregiver
 * would see a silence indistinguishable from a person in trouble.
 */
class BootReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED &&
            intent.action != Intent.ACTION_MY_PACKAGE_REPLACED
        ) {
            return
        }
        // Nothing to collect until the device has been paired with a subject.
        if (!AppGraph.of(context).pairing.isPaired) return

        CollectorService.start(context)
    }
}
