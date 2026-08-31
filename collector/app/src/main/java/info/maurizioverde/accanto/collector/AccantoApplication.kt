package info.maurizioverde.accanto.collector

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context

class AccantoApplication : Application() {

    override fun onCreate() {
        super.onCreate()
        createNotificationChannels()
    }

    private fun createNotificationChannels() {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        manager.createNotificationChannel(
            NotificationChannel(
                CHANNEL_SERVICE,
                getString(R.string.channel_service),
                NotificationManager.IMPORTANCE_LOW,
            ).apply {
                description = getString(R.string.channel_service_description)
                setShowBadge(false)
            },
        )

        // Rung 3 lands here. Importance must be HIGH so Mi Fitness mirrors it to
        // the watch: that mirroring is the only way to make the wrist buzz.
        manager.createNotificationChannel(
            NotificationChannel(
                CHANNEL_CONTACT,
                getString(R.string.channel_contact),
                NotificationManager.IMPORTANCE_HIGH,
            ).apply {
                description = getString(R.string.channel_contact_description)
                enableVibration(true)
            },
        )

        // Rung 4. Separate from the above so the subject can silence a discreet
        // buzz without also silencing the one that matters.
        manager.createNotificationChannel(
            NotificationChannel(
                CHANNEL_ALARM,
                getString(R.string.channel_alarm),
                NotificationManager.IMPORTANCE_HIGH,
            ).apply {
                description = getString(R.string.channel_alarm_description)
                enableVibration(true)
                setBypassDnd(true)
            },
        )
    }

    companion object {
        const val CHANNEL_SERVICE = "accanto.service"
        const val CHANNEL_CONTACT = "accanto.contact"
        const val CHANNEL_ALARM = "accanto.alarm"
    }
}
