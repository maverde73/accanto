package info.maurizioverde.accanto.collector.collect

import android.content.Context
import android.util.Log
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.HeartRateRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import info.maurizioverde.accanto.collector.domain.HealthMapping
import java.time.Instant

/**
 * Reads what Mi Fitness has written into Health Connect.
 *
 * This is the only channel to the watch. Xiaomi Vela is not programmable and
 * exposes no SDK, so the watch is a source of data and Mi Fitness is the gateway
 * -- we read what it deposits rather than talking to the device.
 *
 * Read-only, and only heart rate and steps: sleep and everything else are not
 * needed by the presence model, and asking for them would be permission the
 * subject grants for nothing.
 */
class HealthConnectReader(private val context: Context) {

    private val client: HealthConnectClient? by lazy {
        runCatching {
            if (HealthConnectClient.getSdkStatus(context) == HealthConnectClient.SDK_AVAILABLE) {
                HealthConnectClient.getOrCreate(context)
            } else {
                null
            }
        }.getOrNull()
    }

    val isAvailable: Boolean get() = client != null

    suspend fun hasPermissions(): Boolean {
        val granted = runCatching {
            client?.permissionController?.getGrantedPermissions().orEmpty()
        }.getOrDefault(emptySet())
        return REQUIRED_PERMISSIONS.all { it in granted }
    }

    /**
     * Heart-rate samples in a window, filtered and thinned.
     *
     * The window is bounded rather than open-ended: after a long outage Mi
     * Fitness can dump days of history at once, and shipping all of it would
     * flood the queue with data that no longer says anything about now.
     */
    suspend fun heartRate(since: Instant, until: Instant): List<HealthMapping.HeartRateSample> {
        val active = client ?: return emptyList()
        return runCatching {
            val response = active.readRecords(
                ReadRecordsRequest(
                    recordType = HeartRateRecord::class,
                    timeRangeFilter = TimeRangeFilter.between(since, until),
                ),
            )
            val samples = response.records.flatMap { record ->
                record.samples.map {
                    HealthMapping.HeartRateSample(
                        epochMillis = it.time.toEpochMilli(),
                        bpm = it.beatsPerMinute.toInt(),
                    )
                }
            }
            val kept = HealthMapping.thin(samples)
            // Logged even when empty. "Nothing arrived" and "nothing was asked
            // for" look identical from outside, and telling them apart is the
            // whole difficulty when a health pipeline stays silent.
            Log.i(
                TAG,
                "heart rate: ${response.records.size} record, ${samples.size} campioni, " +
                    "${kept.size} dopo il filtro, finestra $since..$until",
            )
            kept
        }.getOrElse {
            Log.w(TAG, "heart rate read failed", it)
            emptyList()
        }
    }

    suspend fun steps(since: Instant, until: Instant): List<HealthMapping.StepsBucket> {
        val active = client ?: return emptyList()
        return runCatching {
            val response = active.readRecords(
                ReadRecordsRequest(
                    recordType = StepsRecord::class,
                    timeRangeFilter = TimeRangeFilter.between(since, until),
                ),
            )
            val buckets = HealthMapping.movementBuckets(
                response.records.map {
                    HealthMapping.StepsBucket(
                        startMillis = it.startTime.toEpochMilli(),
                        endMillis = it.endTime.toEpochMilli(),
                        count = it.count,
                    )
                },
            )
            Log.i(TAG, "passi: ${response.records.size} record, ${buckets.size} con movimento")
            buckets
        }.getOrElse {
            Log.w(TAG, "steps read failed", it)
            emptyList()
        }
    }

    companion object {
        private const val TAG = "AccantoHealth"

        val REQUIRED_PERMISSIONS: Set<String> = setOf(
            HealthPermission.getReadPermission(HeartRateRecord::class),
            HealthPermission.getReadPermission(StepsRecord::class),
        )

        /** How far back to look after an outage. Older data is history, not presence. */
        const val MAX_LOOKBACK_MILLIS = 6 * 60 * 60 * 1000L
    }
}
