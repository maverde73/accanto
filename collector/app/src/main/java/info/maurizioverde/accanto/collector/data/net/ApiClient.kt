package info.maurizioverde.accanto.collector.data.net

import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.engine.okhttp.OkHttp
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.http.ContentType
import io.ktor.http.HttpStatusCode
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json

/** Outcome of a call, so callers can tell "try later" from "never try again". */
sealed interface ApiResult<out T> {
    data class Ok<T>(val value: T) : ApiResult<T>

    /** Network, timeout or 5xx. The outbox keeps the data and retries. */
    data class Retryable(val reason: String) : ApiResult<Nothing>

    /**
     * 4xx other than 429. Retrying will not help, and holding the data forever
     * would block the queue behind something the backend will never accept.
     */
    data class Rejected(val status: Int, val reason: String) : ApiResult<Nothing>

    /** The device token is no longer valid: stop and ask to be re-paired. */
    data object Unauthorised : ApiResult<Nothing>
}

class ApiClient(
    private val baseUrl: () -> String,
    private val token: () -> String?,
    engine: HttpClient? = null,
) {
    private val client: HttpClient = engine ?: HttpClient(OkHttp) {
        expectSuccess = false
        install(ContentNegotiation) {
            json(Json { ignoreUnknownKeys = true; encodeDefaults = true })
        }
        install(HttpTimeout) {
            requestTimeoutMillis = 30_000
            connectTimeoutMillis = 15_000
            socketTimeoutMillis = 30_000
        }
    }

    suspend fun sendEvents(batch: EventBatchDto): ApiResult<IngestResultDto> =
        post("/v1/ingest/events", batch)

    suspend fun sendLocations(batch: LocationBatchDto): ApiResult<IngestResultDto> =
        post("/v1/ingest/locations", batch)

    suspend fun sendHeartbeat(beat: HeartbeatDto): ApiResult<IngestResultDto> =
        post("/v1/ingest/heartbeat", beat)

    suspend fun fetchCommand(commandId: String): ApiResult<CommandDto> = request {
        client.get("${baseUrl()}/v1/commands/$commandId") { authorised() }
    }

    suspend fun pendingCommands(): ApiResult<List<CommandDto>> = request {
        client.get("${baseUrl()}/v1/commands/pending/list") { authorised() }
    }

    suspend fun ackCommand(commandId: String, ack: CommandAckDto): ApiResult<Unit> =
        postNoContent("/v1/commands/$commandId/ack", ack)

    suspend fun respondToCommand(commandId: String, response: CommandResponseDto): ApiResult<Unit> =
        postNoContent("/v1/commands/$commandId/response", response)

    suspend fun reportCheckin(checkinId: String, report: CheckinReportDto): ApiResult<Unit> =
        postNoContent("/v1/commands/checkins/$checkinId/report", report)

    // ----------------------------------------------------------------- plumbing

    private suspend inline fun <reified B, reified T> post(path: String, body: B): ApiResult<T> =
        request {
            client.post("${baseUrl()}$path") {
                authorised()
                contentType(ContentType.Application.Json)
                setBody(body)
            }
        }

    private suspend inline fun <reified B> postNoContent(path: String, body: B): ApiResult<Unit> {
        val response = try {
            client.post("${baseUrl()}$path") {
                authorised()
                contentType(ContentType.Application.Json)
                setBody(body)
            }
        } catch (error: Exception) {
            return ApiResult.Retryable(error.message ?: error::class.simpleName ?: "network error")
        }
        return classify(response) { ApiResult.Ok(Unit) }
    }

    private suspend inline fun <reified T> request(
        call: () -> HttpResponse,
    ): ApiResult<T> {
        val response = try {
            call()
        } catch (error: Exception) {
            // Offline, DNS failure, timeout: the data is still in the outbox.
            return ApiResult.Retryable(error.message ?: error::class.simpleName ?: "network error")
        }
        return classify(response) { ApiResult.Ok(response.body<T>()) }
    }

    private suspend inline fun <T> classify(
        response: HttpResponse,
        onSuccess: () -> ApiResult<T>,
    ): ApiResult<T> = when {
        response.status.isSuccess() -> onSuccess()
        response.status == HttpStatusCode.Unauthorized -> ApiResult.Unauthorised
        response.status == HttpStatusCode.TooManyRequests ->
            ApiResult.Retryable("rate limited")
        response.status.value in 500..599 ->
            ApiResult.Retryable("server error ${response.status.value}")
        else -> ApiResult.Rejected(response.status.value, response.status.description)
    }

    private fun io.ktor.client.request.HttpRequestBuilder.authorised() {
        token()?.let { header("Authorization", "Bearer $it") }
    }

    fun close() = client.close()
}
