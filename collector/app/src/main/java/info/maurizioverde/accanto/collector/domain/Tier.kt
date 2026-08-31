package info.maurizioverde.accanto.collector.domain

/**
 * Signal taxonomy, mirroring `backend/app/domain/tiers.py`.
 *
 * The tier is authoritative on the server, which derives it from the kind and
 * ignores whatever the collector claims. It is duplicated here only so the app
 * can reason locally about what it has gathered.
 */
enum class Tier(val code: String) {
    /** The subject is conscious and capable. Conclusive. */
    INTERACTION("A"),

    /** The subject is moving. Consciousness very likely. */
    MOVEMENT("B"),

    /** The subject is alive. Says nothing about consciousness. */
    VITAL("C"),

    /** Neither: proves only that the pipeline is working. */
    CONTACT("D"),
}

enum class Source(val code: String) {
    PHONE("phone"),
    WATCH("watch"),
}

enum class EventKind(val code: String, val tier: Tier) {
    UNLOCK("unlock", Tier.INTERACTION),
    APP_USAGE("app_usage", Tier.INTERACTION),
    CHARGER_CONNECTED("charger_connected", Tier.INTERACTION),
    CONFIRMATION("confirmation", Tier.INTERACTION),

    ACTIVITY("activity", Tier.MOVEMENT),
    STEPS("steps", Tier.MOVEMENT),
    LOCATION_MOVE("location_move", Tier.MOVEMENT),

    HR("hr", Tier.VITAL),

    BT_CONTACT("bt_contact", Tier.CONTACT),
    HEARTBEAT("heartbeat", Tier.CONTACT),

    /**
     * Deliberately Tier D. A notification or lift-to-wake turns the screen on
     * without the person doing anything, so treating it as interaction would
     * produce a reassuring "active" from nobody at all.
     */
    SCREEN_ON("screen_on", Tier.CONTACT),
}
