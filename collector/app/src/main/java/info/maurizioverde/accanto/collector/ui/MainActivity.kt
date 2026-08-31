package info.maurizioverde.accanto.collector.ui

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            AccantoTheme {
                Surface(modifier = Modifier.fillMaxSize(), color = AccantoColors.Background) {
                    HomePlaceholder()
                }
            }
        }
    }
}

/**
 * Placeholder home.
 *
 * The real screen follows the collector mockup: what the caregiver can see
 * right now, the permission dashboard, and the access log. It is deliberately
 * not built yet -- the service and the outbox come first, since a beautiful
 * screen over a pipeline that dies after three days is worse than nothing.
 */
@Composable
private fun HomePlaceholder() {
    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text(
            text = "Accanto",
            style = MaterialTheme.typography.headlineMedium,
            color = AccantoColors.Ink,
        )
        Text(
            text = "Collector in costruzione.",
            style = MaterialTheme.typography.bodyMedium,
            color = AccantoColors.InkMuted,
        )
    }
}
