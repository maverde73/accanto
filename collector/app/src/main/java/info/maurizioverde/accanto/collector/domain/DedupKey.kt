package info.maurizioverde.accanto.collector.domain

import java.security.MessageDigest

/**
 * Deterministic deduplication keys, matching `backend/app/domain/dedup.py`.
 *
 * The collector resends its outbox after every disconnection, so a repeat must
 * be recognisable as the same event. The key is derived from the event's own
 * identity -- never from a random id or the moment of sending -- and both sides
 * must compute it identically or duplicated steps would inflate the count.
 */
object DedupKey {

    const val DEFAULT_BUCKET_SECONDS = 1L

    fun of(
        subjectId: String,
        source: String,
        kind: String,
        occurredAtEpochMillis: Long,
        bucketSeconds: Long = DEFAULT_BUCKET_SECONDS,
    ): String {
        require(bucketSeconds >= 1) { "bucketSeconds must be >= 1" }
        val bucket = Math.floorDiv(occurredAtEpochMillis / 1000, bucketSeconds)
        return sha256("$subjectId|$source|$kind|$bucket").take(32)
    }

    fun forLocation(
        subjectId: String,
        occurredAtEpochMillis: Long,
        bucketSeconds: Long = DEFAULT_BUCKET_SECONDS,
    ): String = of(subjectId, "phone", "location_fix", occurredAtEpochMillis, bucketSeconds)

    private fun sha256(input: String): String {
        val bytes = MessageDigest.getInstance("SHA-256").digest(input.toByteArray(Charsets.UTF_8))
        return bytes.joinToString("") { "%02x".format(it) }
    }
}
