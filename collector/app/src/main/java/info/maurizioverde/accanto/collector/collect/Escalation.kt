package info.maurizioverde.accanto.collector.collect

import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.media.RingtoneManager
import android.os.Build
import android.os.CombinedVibration
import android.os.VibrationEffect
import android.os.VibratorManager
import android.util.Log
import androidx.core.app.NotificationCompat
import info.maurizioverde.accanto.collector.AccantoApplication
import info.maurizioverde.accanto.collector.R
import info.maurizioverde.accanto.collector.ui.ConfirmActivity

/**
 * The rungs of the ladder, as they land on the subject's phone.
 *
 * Each is deliberately visible. Nothing here happens silently: the point of the
 * ladder is that the person can tell it is being used, and afterwards see who
 * used it.
 */
object Escalation {

    const val NOTIFICATION_CONTACT = 2001
    const val NOTIFICATION_ALARM = 2002

    /**
     * Rung 3: a discreet nudge that reaches the wrist.
     *
     * We never talk to the watch. Mi Fitness mirrors phone notifications to it,
     * so posting one here is what makes the wrist buzz -- far more robust than
     * driving Mi Fitness's own "find device" screen through an accessibility
     * service that breaks on every update.
     */
    fun nudge(context: Context, commandId: String, message: String) {
        // Tapping has to lead somewhere. The text invites a reply, and a
        // notification that invites a reply and then does nothing when tapped is
        // a promise the app does not keep -- which, in a system whose whole
        // purpose is to be trusted, is worse than sending nothing.
        val reply = Intent(context, ConfirmActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
            .putExtra(ConfirmActivity.EXTRA_COMMAND_ID, commandId)
            .putExtra(ConfirmActivity.EXTRA_MESSAGE, message)

        val pending = PendingIntent.getActivity(
            context,
            commandId.hashCode(),
            reply,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )

        val notification = NotificationCompat.Builder(context, AccantoApplication.CHANNEL_CONTACT)
            .setContentTitle(context.getString(R.string.app_name))
            .setContentText(message)
            .setSmallIcon(R.drawable.ic_notification)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_MESSAGE)
            .setContentIntent(pending)
            .addAction(0, "Sto bene", pending)
            .setAutoCancel(true)
            .build()

        context.getSystemService(NotificationManager::class.java)
            ?.notify(NOTIFICATION_CONTACT, notification)

        vibrate(context, longArrayOf(0, 400, 200, 400))
    }

    /**
     * Rung 4: a sound that gets through.
     *
     * Played on the alarm stream, which by design ignores silent mode, vibrate
     * and most Do Not Disturb configurations. That is why the collector does not
     * need to change the subject's ringer settings and then remember to put them
     * back.
     */
    fun ring(context: Context, durationMillis: Long = 15_000) {
        val uri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
            ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)
            ?: return

        runCatching {
            val player = MediaPlayer()
            player.setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ALARM)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build(),
            )
            player.setDataSource(context, uri)
            player.isLooping = true
            player.setOnPreparedListener { it.start() }
            player.prepareAsync()

            android.os.Handler(context.mainLooper).postDelayed({
                runCatching {
                    if (player.isPlaying) player.stop()
                    player.release()
                }
            }, durationMillis)
        }.onFailure { Log.w(TAG, "could not play the alarm", it) }

        vibrate(context, longArrayOf(0, 800, 400, 800, 400, 800))
    }

    /** Rung 4: the full-screen question, and the answer that settles it. */
    fun askForConfirmation(context: Context, commandId: String, message: String) {
        val activity = Intent(context, ConfirmActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
            .putExtra(ConfirmActivity.EXTRA_COMMAND_ID, commandId)
            .putExtra(ConfirmActivity.EXTRA_MESSAGE, message)

        val fullScreen = PendingIntent.getActivity(
            context,
            commandId.hashCode(),
            activity,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )

        // Posted as a full-screen intent as well as started directly: if the
        // phone is locked, the notification is what surfaces the question.
        val notification = NotificationCompat.Builder(context, AccantoApplication.CHANNEL_ALARM)
            .setContentTitle(context.getString(R.string.app_name))
            .setContentText(message)
            .setSmallIcon(R.drawable.ic_notification)
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_CALL)
            .setFullScreenIntent(fullScreen, true)
            .setOngoing(true)
            .build()

        context.getSystemService(NotificationManager::class.java)
            ?.notify(NOTIFICATION_ALARM, notification)

        runCatching { context.startActivity(activity) }
            .onFailure { Log.i(TAG, "could not start the prompt directly; notification stands") }

        ring(context)
    }

    fun dismissAlarm(context: Context) {
        context.getSystemService(NotificationManager::class.java)?.cancel(NOTIFICATION_ALARM)
    }

    private fun vibrate(context: Context, pattern: LongArray) {
        val manager = context.getSystemService(VibratorManager::class.java) ?: return
        val effect = VibrationEffect.createWaveform(pattern, -1)
        runCatching {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                manager.vibrate(CombinedVibration.createParallel(effect))
            } else {
                @Suppress("DEPRECATION")
                manager.defaultVibrator.vibrate(effect)
            }
        }.onFailure { Log.w(TAG, "vibration failed", it) }
    }

    private const val TAG = "AccantoEscalation"
}
