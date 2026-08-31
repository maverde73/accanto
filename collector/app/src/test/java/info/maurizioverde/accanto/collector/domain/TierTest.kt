package info.maurizioverde.accanto.collector.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class TierTest {

    @Test
    fun `screen on is not treated as interaction`() {
        // A notification or lift-to-wake turns the screen on with nobody doing
        // anything. Counting it as interaction would report a reassuring
        // "active" for a phone sitting alone on a table.
        assertEquals(Tier.CONTACT, EventKind.SCREEN_ON.tier)
    }

    @Test
    fun `unlocking is interaction`() {
        assertEquals(Tier.INTERACTION, EventKind.UNLOCK.tier)
    }

    @Test
    fun `a pressed confirmation is interaction`() {
        assertEquals(Tier.INTERACTION, EventKind.CONFIRMATION.tier)
    }

    @Test
    fun `heart rate proves life, not consciousness`() {
        assertEquals(Tier.VITAL, EventKind.HR.tier)
    }

    @Test
    fun `bluetooth contact proves neither`() {
        assertEquals(Tier.CONTACT, EventKind.BT_CONTACT.tier)
    }

    @Test
    fun `tier codes match the backend`() {
        assertEquals("A", Tier.INTERACTION.code)
        assertEquals("B", Tier.MOVEMENT.code)
        assertEquals("C", Tier.VITAL.code)
        assertEquals("D", Tier.CONTACT.code)
    }
}

class DebouncerTest {

    @Test
    fun `first event of a kind is accepted`() {
        val debouncer = Debouncer(windowMillis = 30_000)
        assertTrue(debouncer.accept(EventKind.UNLOCK, Source.PHONE, 1_000))
    }

    @Test
    fun `a rapid repeat is dropped`() {
        // Unlocks can fire dozens of times a minute; without this the outbox
        // grows without adding information.
        val debouncer = Debouncer(windowMillis = 30_000)
        debouncer.accept(EventKind.UNLOCK, Source.PHONE, 1_000)
        assertFalse(debouncer.accept(EventKind.UNLOCK, Source.PHONE, 5_000))
    }

    @Test
    fun `a repeat after the window is accepted`() {
        val debouncer = Debouncer(windowMillis = 30_000)
        debouncer.accept(EventKind.UNLOCK, Source.PHONE, 1_000)
        assertTrue(debouncer.accept(EventKind.UNLOCK, Source.PHONE, 40_000))
    }

    @Test
    fun `different kinds do not debounce each other`() {
        val debouncer = Debouncer(windowMillis = 30_000)
        debouncer.accept(EventKind.UNLOCK, Source.PHONE, 1_000)
        assertTrue(debouncer.accept(EventKind.STEPS, Source.PHONE, 2_000))
    }

    @Test
    fun `the same kind from watch and phone are tracked separately`() {
        val debouncer = Debouncer(windowMillis = 30_000)
        debouncer.accept(EventKind.STEPS, Source.PHONE, 1_000)
        assertTrue(debouncer.accept(EventKind.STEPS, Source.WATCH, 2_000))
    }
}
