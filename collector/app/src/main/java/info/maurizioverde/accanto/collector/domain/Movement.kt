package info.maurizioverde.accanto.collector.domain

/**
 * Activity recognition, reduced to what the presence model needs.
 *
 * Mapped to a local enum rather than carrying Play Services constants around,
 * so the decision of what counts as evidence stays testable.
 */
enum class MovementKind {
    STILL,
    WALKING,
    RUNNING,
    ON_BICYCLE,
    IN_VEHICLE,
    UNKNOWN,
}

object Movement {

    /** Below this the classifier is guessing, and a guess is not evidence. */
    const val MIN_CONFIDENCE = 60

    /**
     * Whether an activity is evidence that the person is moving.
     *
     * IN_VEHICLE counts, and is quietly one of the most useful signals in the
     * whole system: it explains a large share of unanswered calls on its own.
     * STILL does not -- a phone can be still because its owner is asleep, or
     * because it was left on a table.
     */
    fun isEvidence(kind: MovementKind, confidence: Int): Boolean {
        if (confidence < MIN_CONFIDENCE) return false
        return when (kind) {
            MovementKind.WALKING,
            MovementKind.RUNNING,
            MovementKind.ON_BICYCLE,
            MovementKind.IN_VEHICLE,
            -> true

            MovementKind.STILL, MovementKind.UNKNOWN -> false
        }
    }

    /** Wording for the caregiver, kept out of the UI layer so it is testable. */
    fun label(kind: MovementKind): String = when (kind) {
        MovementKind.WALKING -> "a piedi"
        MovementKind.RUNNING -> "di corsa"
        MovementKind.ON_BICYCLE -> "in bicicletta"
        MovementKind.IN_VEHICLE -> "in auto"
        MovementKind.STILL -> "ferma"
        MovementKind.UNKNOWN -> "non determinata"
    }
}
