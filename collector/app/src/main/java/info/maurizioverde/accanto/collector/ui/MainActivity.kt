package info.maurizioverde.accanto.collector.ui

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember
import info.maurizioverde.accanto.collector.collect.CollectorService
import info.maurizioverde.accanto.collector.collect.Permissions
import info.maurizioverde.accanto.collector.data.AppGraph

class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        val graph = AppGraph.of(this)

        setContent {
            AccantoTheme {
                Surface(modifier = Modifier.fillMaxSize(), color = AccantoColors.Background) {
                    var paired by remember { mutableStateOf(graph.pairing.isPaired) }
                    var subjectName by remember { mutableStateOf(graph.pairing.subjectId) }

                    if (!paired) {
                        PairingScreen(initialApiUrl = graph.pairing.apiUrl) { token, subjectId, name, url ->
                            graph.pairing.apiUrl = url
                            graph.pairing.deviceToken = token
                            graph.pairing.subjectId = subjectId
                            subjectName = name
                            paired = true
                            // Deliberately not started here. Android refuses a
                            // health or location foreground service until a
                            // backing runtime permission is held, and starting
                            // anyway crashes the app the moment pairing
                            // succeeds. The dashboard starts it once granted.
                        }
                    } else {
                        HomeScreen(subjectName ?: "")
                    }
                }
            }
        }
    }
}

@Composable
private fun HomeScreen(subjectName: String) {
    val context = androidx.compose.ui.platform.LocalContext.current
    var permissions by remember { mutableStateOf(Permissions.inspect(context)) }

    // Permissions change in Settings, outside this app. Re-reading them on every
    // resume is the only way the dashboard tells the truth rather than showing
    // whatever was true when the screen was first drawn.
    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                permissions = Permissions.inspect(context)
                // Retry here rather than only once at pairing: the service may
                // have been refused earlier for want of a permission that has
                // since been granted, and the user should not have to know that.
                if (permissions.canRunService) CollectorService.start(context)
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp),
    ) {
        Column {
            Text(
                "Ciao",
                style = MaterialTheme.typography.headlineSmall,
                color = AccantoColors.Ink,
            )
            Text(
                if (permissions.allGranted) {
                    "Tutto funziona come dovrebbe"
                } else {
                    "Serve la tua attenzione"
                },
                style = MaterialTheme.typography.bodyMedium,
                color = AccantoColors.InkMuted,
            )
        }

        PermissionScreen(state = permissions) {
            permissions = Permissions.inspect(context)
        }
    }
}
