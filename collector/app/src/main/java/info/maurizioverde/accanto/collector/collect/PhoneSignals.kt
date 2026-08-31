package info.maurizioverde.accanto.collector.collect

import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import info.maurizioverde.accanto.collector.domain.EventKind

/**
 * The phone's own signals.
 *
 * Counter-intuitively these matter more than the watch's. The phone is fully
 * programmable and its evidence is real-time; the watch only reports in batches
 * through Mi Fitness. And an unlock proves more than a heartbeat: a normal BPM
 * is equally consistent with someone asleep or unconscious, while unlocking a
 * phone takes intent.
 *
 * All of it is event-driven rather than polled, so the steady-state cost is
 * close to nothing.
 */
class PhoneSignals(
    private val context: Context,
    private val onSignal: (EventKind, Long) -> Unit,
) {

    private var receiver: BroadcastReceiver? = null

    fun start() {
        if (receiver != null) return

        val filter = IntentFilter().apply {
            // The strongest and cheapest liveness signal available.
            addAction(Intent.ACTION_USER_PRESENT)
            // Tier D: a notification can raise the screen with nobody there.
            addAction(Intent.ACTION_SCREEN_ON)
            // Plugging in a charger is a deliberate physical act, so Tier A.
            addAction(Intent.ACTION_POWER_CONNECTED)
        }

        receiver = object : BroadcastReceiver() {
            override fun onReceive(ctx: Context?, intent: Intent?) {
                val now = System.currentTimeMillis()
                when (intent?.action) {
                    Intent.ACTION_USER_PRESENT -> onSignal(EventKind.UNLOCK, now)
                    Intent.ACTION_SCREEN_ON -> onSignal(EventKind.SCREEN_ON, now)
                    Intent.ACTION_POWER_CONNECTED -> onSignal(EventKind.CHARGER_CONNECTED, now)
                }
            }
        }

        // Registered at runtime, not in the manifest: since Android 8 these
        // broadcasts are not delivered to manifest-declared receivers, which is
        // precisely why the foreground service has to stay alive.
        context.registerReceiver(receiver, filter)
    }

    fun stop() {
        receiver?.let { runCatching { context.unregisterReceiver(it) } }
        receiver = null
    }

    fun batteryPercent(): Int? {
        val manager = context.getSystemService(Context.BATTERY_SERVICE) as? BatteryManager
            ?: return null
        val level = manager.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
        return level.takeIf { it in 0..100 }
    }

    /**
     * Whether the watch is currently within Bluetooth range.
     *
     * Proves the watch is near the phone, nothing about the person -- which is
     * exactly its job: telling "no data" apart from "sitting still".
     */
    fun watchConnected(): Boolean {
        val manager = context.getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager
            ?: return false
        val adapter: BluetoothAdapter = manager.adapter ?: return false
        if (!adapter.isEnabled) return false

        return runCatching {
            manager.getConnectedDevices(BluetoothProfile.GATT).isNotEmpty() ||
                adapter.getProfileConnectionState(BluetoothProfile.HEADSET) ==
                BluetoothProfile.STATE_CONNECTED
        }.getOrDefault(false)
        // A SecurityException here means BLUETOOTH_CONNECT was revoked; the
        // heartbeat reports permissions_ok=false and the backend shows it as
        // pipeline health rather than as a silent person.
    }
}
