package info.maurizioverde.accanto.collector.domain

/**
 * Collapses repeated signals before they reach the outbox.
 *
 * Unlocks can fire dozens of times a minute. The backend's dedup key uses fixed
 * windows aligned to the epoch, which tolerates near-simultaneous repeats but
 * does not guarantee collapsing them -- two events five seconds apart still
 * differ if a bucket boundary falls between. Authoritative debouncing therefore
 * belongs here, where the previous event is known.
 */
class Debouncer(private val windowMillis: Long = 30_000L) {

    private val lastSeen = mutableMapOf<String, Long>()

    /** True if this event should be recorded; false if it repeats a recent one. */
    fun accept(kind: EventKind, source: Source, atMillis: Long): Boolean {
        val key = "${source.code}|${kind.code}"
        val previous = lastSeen[key]
        if (previous != null && atMillis - previous < windowMillis) return false
        lastSeen[key] = atMillis
        return true
    }

    fun reset() = lastSeen.clear()
}
