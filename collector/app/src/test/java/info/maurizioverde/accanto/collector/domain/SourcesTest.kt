package info.maurizioverde.accanto.collector.domain

import info.maurizioverde.accanto.collector.domain.Geo.Fix
import info.maurizioverde.accanto.collector.domain.HealthMapping.HeartRateSample
import info.maurizioverde.accanto.collector.domain.HealthMapping.StepsBucket
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class GeoTest {

    private val turin = Fix(0, 45.0703, 7.6869, 5f)

    @Test
    fun `distance between Turin and Milan is about 125 km`() {
        val milan = Fix(0, 45.4642, 9.1900, 5f)
        val km = Geo.distanceM(turin, milan) / 1000
        assertTrue("got $km km", km in 120.0..130.0)
    }

    @Test
    fun `distance to itself is zero`() {
        assertEquals(0.0, Geo.distanceM(turin, turin), 0.001)
    }

    @Test
    fun `the first fix is always stored`() {
        assertTrue(Geo.shouldStore(null, turin))
    }

    @Test
    fun `indoor drift is not stored as movement`() {
        // A phone lying on a table produces fixes that wander by tens of metres.
        // Storing them would fill the outbox and show someone pacing their own
        // living room on the map.
        val drifted = Fix(60_000, 45.07033, 7.68693, 30f)
        assertFalse(Geo.shouldStore(turin, drifted))
    }

    @Test
    fun `a real move is stored`() {
        val moved = Fix(60_000, 45.0740, 7.6869, 5f)
        assertTrue(Geo.shouldStore(turin, moved))
    }

    @Test
    fun `a stale position is refreshed even without movement`() {
        val later = Fix(11 * 60_000, 45.0703, 7.6869, 5f)
        assertTrue(Geo.shouldStore(turin, later))
    }

    @Test
    fun `a poor fix must move further to count`() {
        // With 200 m of uncertainty, a 50 m "move" is indistinguishable from
        // noise wearing the costume of a journey.
        val vague = Fix(60_000, 45.0707, 7.6869, 200f)
        assertFalse(Geo.shouldStore(turin, vague))
    }

    @Test
    fun `storing a fix is not the same as claiming movement`() {
        val slightly = Fix(60_000, 45.0708, 7.6869, 5f)
        assertTrue("worth recording", Geo.shouldStore(turin, slightly))
        assertFalse("but not evidence the person is moving", Geo.isMovementEvidence(turin, slightly))
    }

    @Test
    fun `a clear displacement is movement evidence`() {
        val away = Fix(60_000, 45.0780, 7.6869, 5f)
        assertTrue(Geo.isMovementEvidence(turin, away))
    }

    @Test
    fun `there is no movement evidence without a previous fix`() {
        assertFalse(Geo.isMovementEvidence(null, turin))
    }
}

class LocationPolicyTest {

    @Test
    fun `idle mode is cheap`() {
        val spec = LocationPolicy.specFor(LocationMode.IDLE)
        assertFalse(spec.highAccuracy)
        assertTrue(spec.intervalMillis >= 10 * 60_000)
    }

    @Test
    fun `live mode is precise and frequent`() {
        val spec = LocationPolicy.specFor(LocationMode.LIVE)
        assertTrue(spec.highAccuracy)
        assertTrue(spec.intervalMillis <= 10_000)
    }

    @Test
    fun `live mode expires on its own`() {
        // If the caregiver closes the tab without a clean disconnect, the phone
        // must not keep burning GPS until the battery is flat.
        val enabled = 1_000_000L
        assertFalse(LocationPolicy.liveModeExpired(enabled, enabled + 60_000))
        assertTrue(LocationPolicy.liveModeExpired(enabled, enabled + 11 * 60_000))
    }
}

class HealthMappingTest {

    @Test
    fun `implausible readings are discarded`() {
        // A bad optical contact reports nonsense; letting it through would show
        // a caregiver a heart rate of 4.
        assertFalse(HealthMapping.isPlausible(4))
        assertFalse(HealthMapping.isPlausible(400))
        assertTrue(HealthMapping.isPlausible(72))
    }

    @Test
    fun `thinning keeps the shape and drops the bulk`() {
        val samples = (0 until 20).map { HeartRateSample(it * 10_000L, 70 + it) }
        val thinned = HealthMapping.thin(samples, minSpacingMillis = 60_000)
        assertTrue("kept ${thinned.size}", thinned.size in 3..5)
        assertEquals(samples.first(), thinned.first())
    }

    @Test
    fun `thinning removes implausible samples too`() {
        val samples = listOf(
            HeartRateSample(0, 72),
            HeartRateSample(120_000, 500),
            HeartRateSample(240_000, 75),
        )
        val thinned = HealthMapping.thin(samples)
        assertEquals(2, thinned.size)
        assertTrue(thinned.none { it.bpm == 500 })
    }

    @Test
    fun `thinning an empty list is empty, not a crash`() {
        assertTrue(HealthMapping.thin(emptyList()).isEmpty())
    }

    @Test
    fun `out of order samples are sorted before thinning`() {
        val samples = listOf(
            HeartRateSample(240_000, 75),
            HeartRateSample(0, 72),
            HeartRateSample(120_000, 74),
        )
        val thinned = HealthMapping.thin(samples, minSpacingMillis = 60_000)
        assertEquals(listOf(0L, 120_000L, 240_000L), thinned.map { it.epochMillis })
    }

    @Test
    fun `empty step buckets are not evidence of movement`() {
        val buckets = listOf(
            StepsBucket(0, 60_000, 0),
            StepsBucket(60_000, 120_000, 140),
        )
        val kept = HealthMapping.movementBuckets(buckets)
        assertEquals(1, kept.size)
        assertEquals(140L, kept.first().count)
    }

    @Test
    fun `a steps bucket is attributed to its end, not its start`() {
        // The start would claim movement possibly an hour before it happened,
        // and could hold the headline green on stale data.
        val bucket = StepsBucket(startMillis = 0, endMillis = 3_600_000, count = 500)
        assertEquals(3_600_000L, HealthMapping.attributedInstant(bucket))
    }
}

class MovementTest {

    @Test
    fun `walking is evidence`() {
        assertTrue(Movement.isEvidence(MovementKind.WALKING, 85))
    }

    @Test
    fun `being in a vehicle is evidence`() {
        // Quietly one of the most useful signals: it explains a large share of
        // unanswered calls on its own.
        assertTrue(Movement.isEvidence(MovementKind.IN_VEHICLE, 80))
    }

    @Test
    fun `still is never evidence`() {
        // A phone can be still because its owner is asleep, or because it was
        // left on a table.
        assertFalse(Movement.isEvidence(MovementKind.STILL, 99))
    }

    @Test
    fun `a low confidence guess is not evidence`() {
        assertFalse(Movement.isEvidence(MovementKind.WALKING, 30))
    }

    @Test
    fun `unknown is never evidence at any confidence`() {
        assertFalse(Movement.isEvidence(MovementKind.UNKNOWN, 100))
    }

    @Test
    fun `every kind has an Italian label`() {
        for (kind in MovementKind.entries) {
            assertTrue("missing label for $kind", Movement.label(kind).isNotBlank())
        }
    }
}
