package info.maurizioverde.accanto.collector.collect

import android.content.Context
import android.media.AudioAttributes
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.util.Log
import java.util.Locale
import kotlin.coroutines.resume
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeoutOrNull

/**
 * Says something out loud on the subject's phone.
 *
 * Rung 5, outbound. Useful precisely when the person cannot reach the phone: a
 * voice from the speaker needs nothing from them, unlike every rung below it.
 *
 * Spoken on the alarm stream, which by design ignores silent mode and most Do
 * Not Disturb settings -- the same reason rung 4 uses it. A message that a
 * silenced phone swallows would be the loudest rung of the ladder failing at
 * the one thing it is for.
 *
 * The message is always prefixed with who sent it. An announcement that names
 * nobody is barely an announcement, and the subject is entitled to know who is
 * speaking into their room.
 */
class Speaker(private val context: Context) {

    private var engine: TextToSpeech? = null

    private suspend fun ready(): TextToSpeech? {
        engine?.let { return it }

        return withTimeoutOrNull(INIT_TIMEOUT_MILLIS) {
            suspendCancellableCoroutine { cont ->
                var created: TextToSpeech? = null
                created = TextToSpeech(context) { status ->
                    if (status == TextToSpeech.SUCCESS) {
                        created?.language = Locale.ITALIAN
                        created?.setAudioAttributes(
                            AudioAttributes.Builder()
                                .setUsage(AudioAttributes.USAGE_ALARM)
                                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                                .build(),
                        )
                        engine = created
                        if (cont.isActive) cont.resume(created)
                    } else {
                        Log.w(TAG, "text-to-speech non inizializzabile (status $status)")
                        if (cont.isActive) cont.resume(null)
                    }
                }
            }
        }
    }

    /**
     * Speaks the message and waits until it finishes.
     *
     * Returns false if speech was unavailable, so the caller can report an
     * honest failure rather than an execution that produced silence.
     */
    suspend fun announce(from: String?, message: String): Boolean {
        val tts = ready() ?: return false

        val spoken = if (from.isNullOrBlank()) {
            "Messaggio da Accanto. $message"
        } else {
            "$from ti manda un messaggio. $message"
        }

        return withTimeoutOrNull(SPEAK_TIMEOUT_MILLIS) {
            suspendCancellableCoroutine { cont ->
                val id = "accanto-${System.currentTimeMillis()}"
                tts.setOnUtteranceProgressListener(
                    object : UtteranceProgressListener() {
                        override fun onStart(utteranceId: String?) = Unit
                        override fun onDone(utteranceId: String?) {
                            if (cont.isActive) cont.resume(true)
                        }

                        @Deprecated("required by the platform interface")
                        override fun onError(utteranceId: String?) {
                            if (cont.isActive) cont.resume(false)
                        }

                        override fun onError(utteranceId: String?, errorCode: Int) {
                            if (cont.isActive) cont.resume(false)
                        }
                    },
                )
                // QUEUE_FLUSH: a newer message replaces one still playing rather
                // than queueing behind it. Two caregivers talking over each
                // other helps nobody.
                val result = tts.speak(spoken, TextToSpeech.QUEUE_FLUSH, null, id)
                if (result != TextToSpeech.SUCCESS && cont.isActive) cont.resume(false)
            }
        } ?: false
    }

    fun release() {
        engine?.shutdown()
        engine = null
    }

    private companion object {
        const val TAG = "AccantoSpeaker"
        const val INIT_TIMEOUT_MILLIS = 10_000L
        const val SPEAK_TIMEOUT_MILLIS = 60_000L
    }
}
