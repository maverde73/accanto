package info.maurizioverde.accanto.collector.ui

import android.content.Intent
import androidx.activity.compose.rememberLauncherForActivityResult
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
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import info.maurizioverde.accanto.collector.collect.HealthConnectReader

/**
 * Health Connect permissions, requested from inside the app.
 *
 * These are not ordinary runtime permissions: they live in Health Connect, are
 * granted through its own dialog, and cannot be granted by adb. Without this row
 * the only route was for someone to go hunting through four levels of system
 * settings -- and the whole reason the heart rate never appeared during testing
 * was that nobody had.
 *
 * The state is read asynchronously, so it manages its own rather than joining
 * the synchronous [info.maurizioverde.accanto.collector.collect.PermissionState].
 */
@Composable
fun HealthPermissionRow(onChanged: () -> Unit = {}) {
    val context = LocalContext.current
    val reader = remember { HealthConnectReader(context) }

    var available by remember { mutableStateOf(true) }
    var granted by remember { mutableStateOf(false) }
    var refreshToken by remember { mutableStateOf(0) }

    LaunchedEffect(refreshToken) {
        available = reader.isAvailable
        granted = available && reader.hasPermissions()
    }

    val launcher = rememberLauncherForActivityResult(
        PermissionController.createRequestPermissionResultContract(),
    ) {
        refreshToken += 1
        onChanged()
    }

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(AccantoColors.Surface)
            .clickable(enabled = !granted) {
                if (available) {
                    launcher.launch(HealthConnectReader.REQUIRED_PERMISSIONS)
                } else {
                    // Health Connect missing or disabled: send them to it rather
                    // than leaving a dead row that does nothing when tapped.
                    runCatching {
                        context.startActivity(
                            Intent(HealthConnectClient.ACTION_HEALTH_CONNECT_SETTINGS),
                        )
                    }
                }
            }
            .padding(14.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(
                "Dati salute (battito, passi)",
                style = MaterialTheme.typography.bodyLarge,
                color = AccantoColors.Ink,
            )
            Text(
                when {
                    !available -> "Health Connect non disponibile"
                    granted -> "Attivo"
                    else -> "Tocca per consentire la lettura"
                },
                style = MaterialTheme.typography.bodySmall,
                color = if (granted) AccantoColors.InkFaint else AccantoColors.Amber,
            )
        }
        Column(
            modifier = Modifier
                .size(12.dp)
                .clip(RoundedCornerShape(6.dp))
                .background(if (granted) AccantoColors.Green else AccantoColors.Amber),
        ) {}
    }
}
