package info.maurizioverde.accanto.collector.collect

import android.content.Context
import android.media.AudioManager
import android.util.Log
import info.maurizioverde.accanto.collector.data.net.ApiResult
import info.maurizioverde.accanto.collector.data.net.AudioSessionDto
import info.maurizioverde.accanto.collector.data.net.SignalDto
import info.maurizioverde.accanto.collector.data.net.SignalIn
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.webrtc.AudioSource
import org.webrtc.AudioTrack
import org.webrtc.DefaultVideoDecoderFactory
import org.webrtc.DefaultVideoEncoderFactory
import org.webrtc.EglBase
import org.webrtc.IceCandidate
import org.webrtc.MediaConstraints
import org.webrtc.MediaStream
import org.webrtc.PeerConnection
import org.webrtc.PeerConnectionFactory
import org.webrtc.SdpObserver
import org.webrtc.SessionDescription

/**
 * A hands-free two-way call on the subject's phone.
 *
 * The phone is the one that offers. It creates the offer only *after* the
 * announcement has been spoken, so the microphone never opens before the person
 * has been told who is calling and by whom.
 *
 * Signalling is polled over the same authenticated HTTPS as everything else.
 * Audio only: no camera, and the code has no way to acquire one.
 */
class AudioCall(
    private val context: Context,
    private val scope: CoroutineScope,
    private val api: AudioSignalling,
) {

    /** The subset of the API this needs, so the call can be reasoned about alone. */
    interface AudioSignalling {
        suspend fun session(sessionId: String): ApiResult<AudioSessionDto>
        suspend fun markAnnounced(sessionId: String): ApiResult<Unit>
        suspend fun postSignal(sessionId: String, signal: SignalIn): ApiResult<Unit>
        suspend fun readSignals(sessionId: String, since: Long): ApiResult<List<SignalDto>>
        suspend fun endSession(sessionId: String, by: String): ApiResult<Unit>
    }

    private var factory: PeerConnectionFactory? = null
    private var connection: PeerConnection? = null
    private var audioSource: AudioSource? = null
    private var audioTrack: AudioTrack? = null
    private var pollJob: Job? = null
    private var previousAudioMode: Int? = null

    val isActive: Boolean get() = connection != null

    /** Starts the call. Returns false if it could not be established. */
    suspend fun start(sessionId: String): Boolean {
        val servers = when (val s = api.session(sessionId)) {
            is ApiResult.Ok -> iceServers(s.value)
            else -> {
                Log.w(TAG, "sessione non recuperabile")
                return false
            }
        }

        return runCatching {
            initialiseFactory()
            routeToSpeaker()

            val pc = createConnection(servers, sessionId) ?: return false
            connection = pc

            addMicrophone(pc)
            pollJob = scope.launch { pollSignals(sessionId) }
            createAndSendOffer(pc, sessionId)
            true
        }.getOrElse {
            Log.w(TAG, "avvio chiamata fallito", it)
            stop(sessionId, by = "subject")
            false
        }
    }

    suspend fun stop(sessionId: String?, by: String) {
        pollJob?.cancel()
        pollJob = null

        runCatching { connection?.close() }
        connection = null
        runCatching { audioTrack?.dispose() }
        audioTrack = null
        runCatching { audioSource?.dispose() }
        audioSource = null

        restoreAudioMode()
        if (sessionId != null) runCatching { api.endSession(sessionId, by) }
    }

    // ------------------------------------------------------------------ webrtc

    private fun initialiseFactory() {
        if (factory != null) return
        PeerConnectionFactory.initialize(
            PeerConnectionFactory.InitializationOptions.builder(context)
                .createInitializationOptions(),
        )
        val egl = EglBase.create().eglBaseContext
        factory = PeerConnectionFactory.builder()
            .setVideoEncoderFactory(DefaultVideoEncoderFactory(egl, true, true))
            .setVideoDecoderFactory(DefaultVideoDecoderFactory(egl))
            .createPeerConnectionFactory()
    }

    private fun createConnection(
        servers: List<PeerConnection.IceServer>,
        sessionId: String,
    ): PeerConnection? {
        val config = PeerConnection.RTCConfiguration(servers).apply {
            sdpSemantics = PeerConnection.SdpSemantics.UNIFIED_PLAN
            continualGatheringPolicy = PeerConnection.ContinualGatheringPolicy.GATHER_CONTINUALLY
        }

        return factory?.createPeerConnection(
            config,
            object : MinimalObserver() {
                override fun onIceCandidate(candidate: IceCandidate?) {
                    val c = candidate ?: return
                    scope.launch {
                        api.postSignal(sessionId, SignalIn("ice", encodeIce(c)))
                    }
                }

                override fun onConnectionChange(state: PeerConnection.PeerConnectionState?) {
                    Log.i(TAG, "stato connessione: $state")
                    if (state == PeerConnection.PeerConnectionState.FAILED ||
                        state == PeerConnection.PeerConnectionState.CLOSED
                    ) {
                        scope.launch { stop(sessionId, by = "subject") }
                    }
                }
            },
        )
    }

    private fun addMicrophone(pc: PeerConnection) {
        val source = factory!!.createAudioSource(
            MediaConstraints().apply {
                // Hands-free from a phone that may be in a pocket or on a table:
                // the processing matters more here than in a held call.
                mandatory.add(MediaConstraints.KeyValuePair("googEchoCancellation", "true"))
                mandatory.add(MediaConstraints.KeyValuePair("googNoiseSuppression", "true"))
                mandatory.add(MediaConstraints.KeyValuePair("googAutoGainControl", "true"))
            },
        )
        val track = factory!!.createAudioTrack("accanto-mic", source)
        pc.addTrack(track, listOf("accanto"))
        audioSource = source
        audioTrack = track
    }

    private suspend fun createAndSendOffer(pc: PeerConnection, sessionId: String) {
        val constraints = MediaConstraints().apply {
            mandatory.add(MediaConstraints.KeyValuePair("OfferToReceiveAudio", "true"))
            mandatory.add(MediaConstraints.KeyValuePair("OfferToReceiveVideo", "false"))
        }
        pc.createOffer(
            object : MinimalSdpObserver() {
                override fun onCreateSuccess(sdp: SessionDescription?) {
                    val offer = sdp ?: return
                    pc.setLocalDescription(MinimalSdpObserver(), offer)
                    scope.launch { api.postSignal(sessionId, SignalIn("offer", offer.description)) }
                }
            },
            constraints,
        )
    }

    private suspend fun pollSignals(sessionId: String) {
        var since = 0L
        while (scope.isActive && connection != null) {
            when (val result = api.readSignals(sessionId, since)) {
                is ApiResult.Ok -> {
                    for (signal in result.value) {
                        since = maxOf(since, signal.id)
                        applySignal(signal)
                    }
                }
                // A session ended or expired server-side must tear the call down
                // here too, or the microphone would stay open on a call the
                // other side has already left.
                is ApiResult.Rejected -> { stop(sessionId, by = "timeout"); return }
                else -> Unit
            }
            delay(POLL_MILLIS)
        }
    }

    private fun applySignal(signal: SignalDto) {
        val pc = connection ?: return
        when (signal.kind) {
            "answer" -> pc.setRemoteDescription(
                MinimalSdpObserver(),
                SessionDescription(SessionDescription.Type.ANSWER, signal.payload),
            )
            "ice" -> runCatching { pc.addIceCandidate(decodeIce(signal.payload)) }
            else -> Unit
        }
    }

    // ------------------------------------------------------------------- audio

    /** Hands-free: the person may not be able to pick the phone up at all. */
    private fun routeToSpeaker() {
        val manager = context.getSystemService(AudioManager::class.java) ?: return
        previousAudioMode = manager.mode
        manager.mode = AudioManager.MODE_IN_COMMUNICATION
        runCatching {
            val speaker = manager.availableCommunicationDevices
                .firstOrNull { it.type == android.media.AudioDeviceInfo.TYPE_BUILTIN_SPEAKER }
            if (speaker != null) manager.setCommunicationDevice(speaker)
        }
    }

    private fun restoreAudioMode() {
        val manager = context.getSystemService(AudioManager::class.java) ?: return
        runCatching { manager.clearCommunicationDevice() }
        previousAudioMode?.let { manager.mode = it }
        previousAudioMode = null
    }

    private fun iceServers(dto: AudioSessionDto): List<PeerConnection.IceServer> =
        dto.iceServers.mapNotNull { entry ->
            val urls = entry["urls"]?.jsonPrimitive?.content ?: return@mapNotNull null
            PeerConnection.IceServer.builder(urls)
                .setUsername(entry["username"]?.jsonPrimitive?.content ?: "")
                .setPassword(entry["credential"]?.jsonPrimitive?.content ?: "")
                .createIceServer()
        }

    private fun encodeIce(c: IceCandidate): String =
        Json.encodeToString(
            IceWire.serializer(),
            IceWire(c.sdp, c.sdpMid ?: "", c.sdpMLineIndex),
        )

    private fun decodeIce(raw: String): IceCandidate {
        val wire = Json.decodeFromString(IceWire.serializer(), raw)
        return IceCandidate(wire.sdpMid, wire.sdpMLineIndex, wire.candidate)
    }

    @kotlinx.serialization.Serializable
    private data class IceWire(val candidate: String, val sdpMid: String, val sdpMLineIndex: Int)

    private companion object {
        const val TAG = "AccantoAudioCall"
        const val POLL_MILLIS = 1_000L
    }
}

/** Only the callbacks this needs; the rest of the interface is noise here. */
private abstract class MinimalObserver : PeerConnection.Observer {
    override fun onSignalingChange(state: PeerConnection.SignalingState?) = Unit
    override fun onIceConnectionChange(state: PeerConnection.IceConnectionState?) = Unit
    override fun onIceConnectionReceivingChange(receiving: Boolean) = Unit
    override fun onIceGatheringChange(state: PeerConnection.IceGatheringState?) = Unit
    override fun onIceCandidatesRemoved(candidates: Array<out IceCandidate>?) = Unit
    override fun onAddStream(stream: MediaStream?) = Unit
    override fun onRemoveStream(stream: MediaStream?) = Unit
    override fun onDataChannel(channel: org.webrtc.DataChannel?) = Unit
    override fun onRenegotiationNeeded() = Unit
}

private open class MinimalSdpObserver : SdpObserver {
    override fun onCreateSuccess(sdp: SessionDescription?) = Unit
    override fun onSetSuccess() = Unit
    override fun onCreateFailure(error: String?) = Unit
    override fun onSetFailure(error: String?) = Unit
}

/** Kept so the JSON shape of an ICE payload has one definition. */
typealias IcePayload = JsonObject
