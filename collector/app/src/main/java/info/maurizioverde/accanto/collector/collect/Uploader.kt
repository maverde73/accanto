package info.maurizioverde.accanto.collector.collect

import android.util.Log
import info.maurizioverde.accanto.collector.data.Mapping
import info.maurizioverde.accanto.collector.data.db.OutboxDao
import info.maurizioverde.accanto.collector.data.net.ApiClient
import info.maurizioverde.accanto.collector.data.net.ApiResult
import info.maurizioverde.accanto.collector.data.net.EventBatchDto
import info.maurizioverde.accanto.collector.data.net.LocationBatchDto
import info.maurizioverde.accanto.collector.domain.Backoff
import kotlinx.coroutines.delay

/**
 * Drains the outbox.
 *
 * Rows are deleted only after the backend confirms them, so a crash mid-upload
 * costs a duplicate send -- which the dedup key makes free -- and never a lost
 * observation.
 */
class Uploader(
    private val dao: OutboxDao,
    private val api: ApiClient,
    private val backoff: Backoff = Backoff(),
    private val batchSize: Int = 200,
    private val onUnauthorised: () -> Unit = {},
) {

    private var consecutiveFailures = 0

    /** One drain pass. Returns whether everything queued was accepted. */
    suspend fun drain(): Boolean {
        val eventsDone = drainEvents()
        val locationsDone = drainLocations()
        val done = eventsDone && locationsDone

        consecutiveFailures = if (done) 0 else consecutiveFailures + 1
        return done
    }

    /** How long to wait before the next attempt, given how it has been going. */
    fun nextDelayMillis(): Long = backoff.delayFor(consecutiveFailures)

    suspend fun awaitBackoff() {
        val wait = nextDelayMillis()
        if (wait > 0) delay(wait)
    }

    private suspend fun drainEvents(): Boolean {
        while (true) {
            val batch = dao.oldestEvents(batchSize)
            if (batch.isEmpty()) return true

            val result = api.sendEvents(EventBatchDto(batch.map { Mapping.toDto(it) }))
            val ids = batch.map { it.id }

            when (result) {
                is ApiResult.Ok -> dao.deleteEvents(ids)
                is ApiResult.Retryable -> {
                    dao.markEventAttempt(ids)
                    Log.i(TAG, "events deferred: ${result.reason}")
                    return false
                }
                is ApiResult.Rejected -> {
                    // The backend will never accept these. Dropping them keeps
                    // the queue moving; keeping them would block every later
                    // observation behind a permanent error.
                    Log.w(TAG, "events rejected (${result.status}): ${result.reason}")
                    dao.deleteEvents(ids)
                }
                ApiResult.Unauthorised -> {
                    onUnauthorised()
                    return false
                }
            }

            if (batch.size < batchSize) return true
        }
    }

    private suspend fun drainLocations(): Boolean {
        while (true) {
            val batch = dao.oldestLocations(batchSize)
            if (batch.isEmpty()) return true

            val result = api.sendLocations(LocationBatchDto(batch.map { Mapping.toDto(it) }))
            val ids = batch.map { it.id }

            when (result) {
                is ApiResult.Ok -> dao.deleteLocations(ids)
                is ApiResult.Retryable -> {
                    dao.markLocationAttempt(ids)
                    return false
                }
                is ApiResult.Rejected -> {
                    Log.w(TAG, "fixes rejected (${result.status}): ${result.reason}")
                    dao.deleteLocations(ids)
                }
                ApiResult.Unauthorised -> {
                    onUnauthorised()
                    return false
                }
            }

            if (batch.size < batchSize) return true
        }
    }

    /**
     * Keeps the queue within what a phone should hold.
     *
     * Only reached after a very long outage. Discarding the oldest movement
     * samples is better than filling the device, and the recent ones -- the only
     * ones that affect presence now -- are the ones kept.
     */
    suspend fun trimIfHuge(maxRows: Int = 50_000) {
        val events = dao.eventCount()
        if (events > maxRows) dao.trimOldestEvents(events - maxRows)

        val fixes = dao.locationCount()
        if (fixes > maxRows) dao.trimOldestLocations(fixes - maxRows)
    }

    private companion object {
        const val TAG = "AccantoUploader"
    }
}
