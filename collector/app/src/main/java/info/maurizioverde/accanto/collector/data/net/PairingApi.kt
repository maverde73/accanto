package info.maurizioverde.accanto.collector.data.net

import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.engine.okhttp.OkHttp
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.HttpStatusCode
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

@Serializable
data class PairRequest(val code: String)

@Serializable
data class PairedResponse(
    @SerialName("device_id") val deviceId: String,
    @SerialName("device_token") val deviceToken: String,
    @SerialName("subject_id") val subjectId: String,
    @SerialName("subject_name") val subjectName: String,
)

/**
 * The one call made before the device has any credential.
 *
 * Separate from [ApiClient] because it is the only unauthenticated request the
 * collector ever makes, and because it must work against a base URL the user
 * has just typed and may well have got wrong.
 */
class PairingApi {

    private val client = HttpClient(OkHttp) {
        expectSuccess = false
        install(ContentNegotiation) { json(Json { ignoreUnknownKeys = true }) }
        install(HttpTimeout) {
            requestTimeoutMillis = 20_000
            connectTimeoutMillis = 10_000
        }
    }

    sealed interface Outcome {
        data class Paired(val response: PairedResponse) : Outcome

        /** Wrong, expired or already used. The backend does not say which, so
         *  the code cannot be probed; the message here says as much. */
        data object BadCode : Outcome

        data object TooManyAttempts : Outcome

        data class Unreachable(val reason: String) : Outcome
    }

    suspend fun pair(baseUrl: String, code: String): Outcome {
        val response = try {
            client.post("${baseUrl.trimEnd('/')}/v1/devices/pair") {
                contentType(ContentType.Application.Json)
                setBody(PairRequest(code))
            }
        } catch (error: Exception) {
            return Outcome.Unreachable(error.message ?: "connessione non riuscita")
        }

        return when {
            response.status.isSuccess() -> Outcome.Paired(response.body())
            response.status == HttpStatusCode.TooManyRequests -> Outcome.TooManyAttempts
            response.status == HttpStatusCode.BadRequest -> Outcome.BadCode
            else -> Outcome.Unreachable("errore ${response.status.value}")
        }
    }

    fun close() = client.close()
}
