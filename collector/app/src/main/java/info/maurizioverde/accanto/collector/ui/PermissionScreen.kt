package info.maurizioverde.accanto.collector.ui

import android.Manifest
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import info.maurizioverde.accanto.collector.collect.PermissionState

/**
 * The permission dashboard.
 *
 * Not a setup convenience. One UI, or an OS update, can revoke a permission
 * months later, and the pipeline then goes quiet with no error anywhere -- a
 * failure that looks exactly like the thing the product exists to detect. This
 * screen is how that becomes visible and fixable by the only person who can fix
 * it.
 *
 * Each row deep-links to the specific system screen, because the alternative is
 * asking someone to find eight settings across five menus.
 */
@Composable
fun PermissionScreen(state: PermissionState, onRefresh: () -> Unit) {
    val context = androidx.compose.ui.platform.LocalContext.current

    val runtimeLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) { onRefresh() }

    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text(
            if (state.allGranted) "Tutti i permessi attivi" else "Manca qualcosa",
            style = MaterialTheme.typography.titleMedium,
            color = AccantoColors.Ink,
        )
        Text(
            if (state.allGranted) {
                "Accanto può raccogliere e inviare i dati come previsto."
            } else {
                "Senza questi permessi alcuni dati smettono di arrivare, e chi ti segue " +
                    "vedrebbe un silenzio che sembra un problema."
            },
            style = MaterialTheme.typography.bodyMedium,
            color = AccantoColors.InkMuted,
        )

        PermissionRow("Posizione", state.fineLocation) {
            runtimeLauncher.launch(
                arrayOf(
                    Manifest.permission.ACCESS_FINE_LOCATION,
                    Manifest.permission.ACCESS_COARSE_LOCATION,
                ),
            )
        }

        // Android 11+ refuses to grant this in the same dialog as the others; it
        // has to be chosen as "Allow all the time" in Settings.
        PermissionRow("Posizione sempre", state.backgroundLocation) {
            openAppSettings(context)
        }

        PermissionRow("Attività fisica", state.activityRecognition) {
            runtimeLauncher.launch(arrayOf(Manifest.permission.ACTIVITY_RECOGNITION))
        }

        PermissionRow("Notifiche", state.notifications) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                runtimeLauncher.launch(arrayOf(Manifest.permission.POST_NOTIFICATIONS))
            }
        }

        PermissionRow("Dispositivi vicini", state.bluetooth) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                runtimeLauncher.launch(arrayOf(Manifest.permission.BLUETOOTH_CONNECT))
            }
        }

        PermissionRow("Accesso all'uso", state.usageStats) {
            context.startActivity(Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS))
        }

        PermissionRow("Sopra altre app", state.overlay) {
            context.startActivity(
                Intent(
                    Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                    Uri.parse("package:${context.packageName}"),
                ),
            )
        }

        PermissionRow("Batteria senza restrizioni", state.batteryUnrestricted) {
            // Asking directly is allowed and far kinder than walking someone
            // through four levels of Settings.
            context.startActivity(
                Intent(
                    Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                    Uri.parse("package:${context.packageName}"),
                ),
            )
        }
    }
}

@Composable
private fun PermissionRow(label: String, granted: Boolean, onFix: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(AccantoColors.Surface)
            .clickable(enabled = !granted, onClick = onFix)
            .padding(14.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(label, style = MaterialTheme.typography.bodyLarge, color = AccantoColors.Ink)
            Text(
                if (granted) "Attivo" else "Tocca per attivare",
                style = MaterialTheme.typography.bodySmall,
                color = if (granted) AccantoColors.InkFaint else AccantoColors.Amber,
            )
        }
        // Colour is never the only cue: the label above says the same thing.
        Column(
            modifier = Modifier
                .size(12.dp)
                .clip(RoundedCornerShape(6.dp))
                .background(if (granted) AccantoColors.Green else AccantoColors.Amber),
        ) {}
    }
}

private fun openAppSettings(context: Context) {
    context.startActivity(
        Intent(
            Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
            Uri.parse("package:${context.packageName}"),
        ),
    )
}
