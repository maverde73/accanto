package info.maurizioverde.accanto.collector.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import info.maurizioverde.accanto.collector.collect.CollectorService
import info.maurizioverde.accanto.collector.data.AppGraph

/**
 * Changes the server address after pairing.
 *
 * The address was editable only on the pairing screen, so moving the backend --
 * from a development machine to a real hostname, say -- meant unpairing and
 * starting over, losing whatever the outbox still held. An address that can
 * only be set once is an address that cannot be corrected.
 *
 * The device token is untouched: it identifies this device to the subject's
 * account, not to a particular host.
 */
@Composable
fun ServerRow() {
    val context = LocalContext.current
    val graph = remember { AppGraph.of(context) }

    var current by remember { mutableStateOf(graph.pairing.apiUrl) }
    var editing by remember { mutableStateOf(false) }
    var draft by remember { mutableStateOf(current) }

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(AccantoColors.Surface)
            .clickable { draft = current; editing = true }
            .padding(14.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text("Server", style = MaterialTheme.typography.bodyLarge, color = AccantoColors.Ink)
            Text(
                current,
                style = MaterialTheme.typography.bodySmall,
                color = AccantoColors.InkFaint,
            )
        }
    }

    if (editing) {
        AlertDialog(
            onDismissRequest = { editing = false },
            title = { Text("Indirizzo del server") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        value = draft,
                        onValueChange = { draft = it },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    Text(
                        "I dati già raccolti restano in coda e verranno inviati al nuovo " +
                            "indirizzo. Il collegamento con la persona non cambia.",
                        style = MaterialTheme.typography.bodySmall,
                        color = AccantoColors.InkMuted,
                    )
                }
            },
            confirmButton = {
                TextButton(
                    enabled = draft.isNotBlank(),
                    onClick = {
                        graph.pairing.apiUrl = draft.trim()
                        current = graph.pairing.apiUrl
                        editing = false
                        // Restart so the running loops pick the new address up
                        // immediately, instead of on the next natural restart.
                        CollectorService.start(context)
                    },
                ) { Text("Salva") }
            },
            dismissButton = { TextButton(onClick = { editing = false }) { Text("Annulla") } },
        )
    }
}
