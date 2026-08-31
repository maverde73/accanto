package info.maurizioverde.accanto.collector.collect

import android.app.NotificationManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * Answers a discreet nudge without opening anything.
 *
 * Rung 3 exists to be quiet. Making its notification open the full-screen
 * rung-4 screen -- which is what an earlier fix did -- collapsed the ladder:
 * three rungs that all ended in the same alarm. The gradation is the product.
 *
 * So the reply here is a single tap on the notification action, and nothing
 * appears on screen at all.
 */
class ResponseReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != ACTION_REPLY) return
        val commandId = intent.getStringExtra(EXTRA_COMMAND_ID) ?: return
        val response = intent.getStringExtra(EXTRA_RESPONSE) ?: return

        context.getSystemService(NotificationManager::class.java)
            ?.cancel(Escalation.NOTIFICATION_CONTACT)

        CollectorService.respondToPrompt(context, commandId, response)
    }

    companion object {
        const val ACTION_REPLY = "info.maurizioverde.accanto.NOTIFICATION_REPLY"
        const val EXTRA_COMMAND_ID = "command_id"
        const val EXTRA_RESPONSE = "response"
    }
}
