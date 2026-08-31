package info.maurizioverde.accanto.collector.data.db

import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Index
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.RoomDatabase

/**
 * The local outbox.
 *
 * Every observation is written here first and only removed once the backend has
 * acknowledged it. That ordering is what makes the collector survive a tunnel,
 * a flat battery or a week without signal: nothing is ever held only in memory.
 *
 * The unique index on `dedupKey` makes the queue itself idempotent, so a source
 * that fires twice for the same instant cannot enqueue the same event twice --
 * a second line of defence in front of the backend's own constraint.
 */

@Entity(
    tableName = "outbox_event",
    indices = [Index(value = ["dedupKey"], unique = true), Index(value = ["occurredAtMillis"])],
)
data class OutboxEvent(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val occurredAtMillis: Long,
    val source: String,
    val kind: String,
    /** Serialised JSON object; the shape varies per kind. */
    val payloadJson: String = "{}",
    val dedupKey: String,
    val attempts: Int = 0,
)

@Entity(
    tableName = "outbox_location",
    indices = [Index(value = ["dedupKey"], unique = true), Index(value = ["occurredAtMillis"])],
)
data class OutboxLocation(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val occurredAtMillis: Long,
    val lat: Double,
    val lon: Double,
    val accuracyM: Float?,
    val speedMps: Float?,
    val batteryPct: Int?,
    val dedupKey: String,
    val attempts: Int = 0,
)

@Dao
interface OutboxDao {

    /** Ignores an event already queued for the same instant and kind. */
    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun enqueueEvent(event: OutboxEvent): Long

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun enqueueLocation(fix: OutboxLocation): Long

    /** Oldest first: the backend orders by `occurred_at`, but sending in order
     *  keeps the snapshot from flapping backwards while a backlog drains. */
    @Query("SELECT * FROM outbox_event ORDER BY occurredAtMillis ASC LIMIT :limit")
    suspend fun oldestEvents(limit: Int): List<OutboxEvent>

    @Query("SELECT * FROM outbox_location ORDER BY occurredAtMillis ASC LIMIT :limit")
    suspend fun oldestLocations(limit: Int): List<OutboxLocation>

    @Query("DELETE FROM outbox_event WHERE id IN (:ids)")
    suspend fun deleteEvents(ids: List<Long>)

    @Query("DELETE FROM outbox_location WHERE id IN (:ids)")
    suspend fun deleteLocations(ids: List<Long>)

    @Query("UPDATE outbox_event SET attempts = attempts + 1 WHERE id IN (:ids)")
    suspend fun markEventAttempt(ids: List<Long>)

    @Query("UPDATE outbox_location SET attempts = attempts + 1 WHERE id IN (:ids)")
    suspend fun markLocationAttempt(ids: List<Long>)

    @Query("SELECT COUNT(*) FROM outbox_event")
    suspend fun eventCount(): Int

    @Query("SELECT COUNT(*) FROM outbox_location")
    suspend fun locationCount(): Int

    /**
     * Drops the oldest entries when the queue has grown past what a phone should
     * hold. Reached only after a very long outage; losing the oldest movement
     * samples is preferable to filling the device's storage.
     */
    @Query(
        "DELETE FROM outbox_event WHERE id IN " +
            "(SELECT id FROM outbox_event ORDER BY occurredAtMillis ASC LIMIT :count)",
    )
    suspend fun trimOldestEvents(count: Int)

    @Query(
        "DELETE FROM outbox_location WHERE id IN " +
            "(SELECT id FROM outbox_location ORDER BY occurredAtMillis ASC LIMIT :count)",
    )
    suspend fun trimOldestLocations(count: Int)
}

@Database(
    entities = [OutboxEvent::class, OutboxLocation::class],
    version = 1,
    exportSchema = false,
)
abstract class AccantoDatabase : RoomDatabase() {
    abstract fun outbox(): OutboxDao
}
