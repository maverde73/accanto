package info.maurizioverde.accanto.collector.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The dedup key must match the backend's byte for byte, or a resent event would
 * be stored twice and inflate the step count.
 *
 * The expected values below are the ones produced by
 * `backend/app/domain/dedup.py` for the same inputs.
 */
class DedupKeyTest {

    private val subject = "11111111-1111-1111-1111-111111111111"
    private val whenMillis = 1_781_267_696_000L // 2026-06-12T12:34:56Z

    // Computed by backend/app/domain/dedup.py for exactly these inputs. If a
    // change here makes them fail, the two implementations have diverged and
    // every resent event would be stored twice.
    @Test
    fun `keys match the backend byte for byte`() {
        assertEquals(
            "0c39c4332798d2bd0d995be4ea75a802",
            DedupKey.of(subject, "phone", "unlock", whenMillis),
        )
        assertEquals(
            "f064113fb36c49feeb6a919b8d532adf",
            DedupKey.of(subject, "phone", "unlock", whenMillis, bucketSeconds = 30),
        )
        assertEquals(
            "67d24c1506af93dbabd32615db8d9da8",
            DedupKey.of(subject, "watch", "steps", whenMillis),
        )
        assertEquals(
            "f2ac4c638695feba864c22bc5f468dd9",
            DedupKey.forLocation(subject, whenMillis),
        )
    }

    @Test
    fun `same event yields the same key`() {
        assertEquals(
            DedupKey.of(subject, "phone", "unlock", whenMillis),
            DedupKey.of(subject, "phone", "unlock", whenMillis),
        )
    }

    @Test
    fun `key varies with the subject`() {
        assertNotEquals(
            DedupKey.of(subject, "phone", "unlock", whenMillis),
            DedupKey.of("22222222-2222-2222-2222-222222222222", "phone", "unlock", whenMillis),
        )
    }

    @Test
    fun `key varies with the source`() {
        assertNotEquals(
            DedupKey.of(subject, "phone", "steps", whenMillis),
            DedupKey.of(subject, "watch", "steps", whenMillis),
        )
    }

    @Test
    fun `key varies with the second`() {
        assertNotEquals(
            DedupKey.of(subject, "phone", "unlock", whenMillis),
            DedupKey.of(subject, "phone", "unlock", whenMillis + 1000),
        )
    }

    @Test
    fun `bucketing collapses repeats inside the same window`() {
        assertEquals(
            DedupKey.of(subject, "phone", "unlock", whenMillis, bucketSeconds = 30),
            DedupKey.of(subject, "phone", "unlock", whenMillis + 1000, bucketSeconds = 30),
        )
    }

    @Test
    fun `key is 32 characters so it fits the indexed column`() {
        assertEquals(32, DedupKey.of(subject, "phone", "unlock", whenMillis).length)
    }

    @Test
    fun `location keys do not collide with activity keys`() {
        assertNotEquals(
            DedupKey.forLocation(subject, whenMillis),
            DedupKey.of(subject, "phone", "unlock", whenMillis),
        )
    }

    @Test
    fun `sub-second precision is folded away, matching the backend`() {
        // The backend truncates to whole seconds; a millisecond difference must
        // not produce a different key or a resend would look like a new event.
        assertEquals(
            DedupKey.of(subject, "phone", "unlock", whenMillis),
            DedupKey.of(subject, "phone", "unlock", whenMillis + 999),
        )
    }

    @Test
    fun `key is lowercase hexadecimal`() {
        assertTrue(DedupKey.of(subject, "phone", "unlock", whenMillis).matches(Regex("[0-9a-f]{32}")))
    }
}
