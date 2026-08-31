package info.maurizioverde.accanto.collector.collect

import info.maurizioverde.accanto.collector.data.AppGraph
import info.maurizioverde.accanto.collector.data.net.ApiResult
import info.maurizioverde.accanto.collector.data.net.AudioSessionDto
import info.maurizioverde.accanto.collector.data.net.SignalDto
import info.maurizioverde.accanto.collector.data.net.SignalIn

/**
 * Connects [AudioCall] to the real API.
 *
 * A thin adapter rather than passing the whole client in, so the call knows only
 * the five operations it needs and can be reasoned about -- and tested -- on its
 * own.
 */
class AudioBridge(private val graph: AppGraph) : AudioCall.AudioSignalling {

    override suspend fun session(sessionId: String): ApiResult<AudioSessionDto> =
        graph.api.audioSession(sessionId)

    override suspend fun markAnnounced(sessionId: String): ApiResult<Unit> =
        graph.api.audioAnnounced(sessionId)

    override suspend fun postSignal(sessionId: String, signal: SignalIn): ApiResult<Unit> =
        graph.api.audioSignal(sessionId, signal)

    override suspend fun readSignals(sessionId: String, since: Long): ApiResult<List<SignalDto>> =
        graph.api.audioSignals(sessionId, since)

    override suspend fun endSession(sessionId: String, by: String): ApiResult<Unit> =
        graph.api.audioEnd(sessionId, by)
}
