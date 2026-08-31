package info.maurizioverde.accanto.collector.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import info.maurizioverde.accanto.collector.data.net.PairingApi
import kotlinx.coroutines.launch

/**
 * First run: connect this phone to a subject.
 *
 * The code is typed by the person being monitored, on their own phone. That is
 * the moment consent becomes concrete -- nobody can enrol this device remotely.
 */
@Composable
fun PairingScreen(
    initialApiUrl: String,
    onPaired: (token: String, subjectId: String, subjectName: String, apiUrl: String) -> Unit,
) {
    var apiUrl by remember { mutableStateOf(initialApiUrl) }
    var code by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    val scope = rememberCoroutineScope()
    val api = remember { PairingApi() }

    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("Accanto", style = MaterialTheme.typography.headlineMedium, color = AccantoColors.Ink)
        Text(
            "Inserisci il codice che ti è stato mostrato per collegare questo telefono.",
            style = MaterialTheme.typography.bodyMedium,
            color = AccantoColors.InkMuted,
        )

        OutlinedTextField(
            value = code,
            onValueChange = { code = it.uppercase() },
            label = { Text("Codice") },
            singleLine = true,
            enabled = !busy,
            keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Characters),
            modifier = Modifier.fillMaxWidth(),
        )

        OutlinedTextField(
            value = apiUrl,
            onValueChange = { apiUrl = it },
            label = { Text("Indirizzo del server") },
            singleLine = true,
            enabled = !busy,
            modifier = Modifier.fillMaxWidth(),
        )

        error?.let {
            Text(it, style = MaterialTheme.typography.bodyMedium, color = AccantoColors.Red)
        }

        Button(
            onClick = {
                busy = true
                error = null
                scope.launch {
                    when (val outcome = api.pair(apiUrl, code)) {
                        is PairingApi.Outcome.Paired -> {
                            val body = outcome.response
                            onPaired(body.deviceToken, body.subjectId, body.subjectName, apiUrl)
                        }
                        PairingApi.Outcome.BadCode ->
                            error = "Codice non valido o scaduto. Fattene generare uno nuovo."
                        PairingApi.Outcome.TooManyAttempts ->
                            error = "Troppi tentativi. Riprova tra qualche minuto."
                        is PairingApi.Outcome.Unreachable ->
                            error = "Server non raggiungibile: ${outcome.reason}"
                    }
                    busy = false
                }
            },
            enabled = !busy && code.isNotBlank() && apiUrl.isNotBlank(),
            modifier = Modifier.fillMaxWidth(),
        ) {
            if (busy) CircularProgressIndicator(modifier = Modifier.padding(4.dp))
            else Text("Collega")
        }
    }
}
