package info.maurizioverde.accanto.collector.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class BackoffTest {

    /** Deterministic: always returns the ceiling, so growth can be asserted. */
    private fun fixed() = Backoff(
        initialMillis = 5_000,
        maxMillis = 900_000,
        factor = 2.0,
        random = { bound -> bound },
    )

    @Test
    fun `first send is immediate`() {
        assertEquals(0L, fixed().delayFor(0))
    }

    @Test
    fun `delay grows exponentially`() {
        val backoff = fixed()
        assertEquals(5_000L, backoff.delayFor(1))
        assertEquals(10_000L, backoff.delayFor(2))
        assertEquals(20_000L, backoff.delayFor(3))
        assertEquals(40_000L, backoff.delayFor(4))
    }

    @Test
    fun `delay is capped`() {
        val backoff = fixed()
        assertEquals(900_000L, backoff.delayFor(50))
    }

    @Test
    fun `cap holds even for absurd attempt counts`() {
        // After a week offline the attempt counter is large; the exponential
        // must not overflow into a nonsensical delay.
        assertEquals(900_000L, fixed().delayFor(1_000))
    }

    @Test
    fun `jitter keeps the delay within the ceiling`() {
        // Without jitter every collector that lost connectivity in the same
        // outage would return at the same instant, hitting the backend exactly
        // as it recovered.
        val backoff = Backoff(initialMillis = 1_000, maxMillis = 60_000, factor = 2.0)
        repeat(200) {
            val delay = backoff.delayFor(4)
            assertTrue("delay $delay outside bounds", delay in 0..backoff.ceilingFor(4))
        }
    }

    @Test
    fun `jitter actually varies`() {
        val backoff = Backoff(initialMillis = 10_000, maxMillis = 600_000, factor = 2.0)
        val seen = (1..50).map { backoff.delayFor(5) }.toSet()
        assertTrue("jitter produced a single value: $seen", seen.size > 1)
    }

    @Test(expected = IllegalArgumentException::class)
    fun `negative attempt is rejected`() {
        fixed().delayFor(-1)
    }
}

class TimestampsTest {

    @Test
    fun `formats with an offset, which the backend requires`() {
        val iso = Timestamps.isoOffset(1_781_267_696_000L, java.time.ZoneId.of("Europe/Rome"))
        // A naive timestamp cannot be placed on a timeline and is refused.
        assertTrue("missing offset in $iso", iso.matches(Regex(".*([+-]\\d{2}:\\d{2}|Z)$")))
        assertTrue(iso.startsWith("2026-06-12T"))
    }

    @Test
    fun `same instant in different zones is the same moment`() {
        val rome = Timestamps.isoOffset(1_781_267_696_000L, java.time.ZoneId.of("Europe/Rome"))
        val utc = Timestamps.isoOffset(1_781_267_696_000L, java.time.ZoneId.of("UTC"))
        assertEquals(
            java.time.OffsetDateTime.parse(rome).toInstant(),
            java.time.OffsetDateTime.parse(utc).toInstant(),
        )
    }

    @Test
    fun `a badly wrong clock is caught before it reaches the queue`() {
        val now = 1_781_267_696_000L
        // Otherwise the event would sit at the head of the outbox forever,
        // refused by the backend and blocking everything behind it.
        assertTrue(Timestamps.isImplausiblyFuture(now + 30 * 60_000, now))
    }

    @Test
    fun `small skew is tolerated`() {
        val now = 1_781_267_696_000L
        assertTrue(!Timestamps.isImplausiblyFuture(now + 2 * 60_000, now))
    }
}
