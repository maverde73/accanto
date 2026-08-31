package info.maurizioverde.accanto.collector.ui

import android.app.KeyguardManager
import android.content.Context
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import info.maurizioverde.accanto.collector.collect.CollectorService
import info.maurizioverde.accanto.collector.collect.Escalation

/**
 * Rung 4: the question that ends the guessing.
 *
 * A pressed "sto bene" is the strongest evidence the whole system can carry --
 * not an inference from an accelerometer or a heart rate, but a statement. It is
 * what all the sensor machinery is trying to approximate.
 *
 * Shown over the lock screen, because a question that waits for someone to
 * unlock their phone is not an answer to "is she all right".
 */
class ConfirmActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        showOverLockScreen()

        val commandId = intent.getStringExtra(EXTRA_COMMAND_ID).orEmpty()
        val message = intent.getStringExtra(EXTRA_MESSAGE) ?: "Tutto bene?"

        setContent {
            AccantoTheme {
                Surface(modifier = Modifier.fillMaxSize(), color = AccantoColors.Background) {
                    ConfirmContent(
                        message = message,
                        onOk = { answer(commandId, "im_ok") },
                        onHelp = { answer(commandId, "need_help") },
                    )
                }
            }
        }
    }

    private fun answer(commandId: String, response: String) {
        Escalation.dismissAlarm(this)
        CollectorService.respondToPrompt(this, commandId, response)
        finish()
    }

    private fun showOverLockScreen() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
            setShowWhenLocked(true)
            setTurnScreenOn(true)
            (getSystemService(Context.KEYGUARD_SERVICE) as? KeyguardManager)
                ?.requestDismissKeyguard(this, null)
        }
    }

    companion object {
        const val EXTRA_COMMAND_ID = "command_id"
        const val EXTRA_MESSAGE = "message"
    }
}

@Composable
private fun ConfirmContent(message: String, onOk: () -> Unit, onHelp: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().padding(28.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            text = message,
            style = MaterialTheme.typography.headlineMedium,
            color = AccantoColors.Ink,
            textAlign = TextAlign.Center,
        )
        Text(
            text = "Qualcuno che ti segue vuole sapere come stai.",
            style = MaterialTheme.typography.bodyLarge,
            color = AccantoColors.InkMuted,
            textAlign = TextAlign.Center,
            modifier = Modifier.padding(top = 12.dp, bottom = 40.dp),
        )

        Button(
            onClick = onOk,
            modifier = Modifier.fillMaxWidth().height(62.dp),
            colors = ButtonDefaults.buttonColors(containerColor = AccantoColors.Green),
        ) {
            Text("Sto bene", style = MaterialTheme.typography.titleMedium)
        }

        Button(
            onClick = onHelp,
            modifier = Modifier.fillMaxWidth().height(62.dp).padding(top = 14.dp),
            colors = ButtonDefaults.buttonColors(containerColor = AccantoColors.Red),
        ) {
            Text("Ho bisogno di aiuto", style = MaterialTheme.typography.titleMedium)
        }
    }
}
