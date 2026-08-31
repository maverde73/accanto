package info.maurizioverde.accanto.collector.data

import android.content.Context
import androidx.room.Room
import info.maurizioverde.accanto.collector.collect.Uploader
import info.maurizioverde.accanto.collector.data.db.AccantoDatabase
import info.maurizioverde.accanto.collector.data.db.OutboxDao
import info.maurizioverde.accanto.collector.data.net.ApiClient

/**
 * Manual dependency wiring.
 *
 * Small enough that a DI framework would add a build step and a learning curve
 * without buying anything. Constructed once per process and shared.
 */
class AppGraph private constructor(context: Context) {

    val pairing = PairingStore(context)

    private val database: AccantoDatabase = Room.databaseBuilder(
        context.applicationContext,
        AccantoDatabase::class.java,
        "accanto.db",
    ).build()

    val outbox: OutboxDao = database.outbox()

    val api = ApiClient(
        baseUrl = { pairing.apiUrl },
        token = { pairing.deviceToken },
    )

    val uploader = Uploader(
        dao = outbox,
        api = api,
        onUnauthorised = {
            // The device token was revoked server-side. Keep the queued data --
            // it is still valid once re-paired -- but stop retrying with a
            // credential that will never be accepted again.
            pairing.deviceToken = null
        },
    )

    companion object {
        @Volatile
        private var instance: AppGraph? = null

        fun of(context: Context): AppGraph =
            instance ?: synchronized(this) {
                instance ?: AppGraph(context.applicationContext).also { instance = it }
            }
    }
}
