package info.maurizioverde.accanto.collector.ui

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

/**
 * Why Accanto asks for health data.
 *
 * Health Connect requires this screen before it will show its permission
 * dialog, and the requirement is a good one: health data is asked for far too
 * casually. The text says exactly what is read, what it is used for, and what
 * is deliberately not asked -- which is also the honest answer to "why does a
 * presence app want my heart rate".
 */
class PermissionsRationaleActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            AccantoTheme {
                Surface(modifier = Modifier.fillMaxSize(), color = AccantoColors.Background) {
                    Column(
                        modifier = Modifier
                            .fillMaxSize()
                            .verticalScroll(rememberScrollState())
                            .padding(24.dp),
                        verticalArrangement = Arrangement.spacedBy(14.dp),
                    ) {
                        Text(
                            "Perché Accanto legge i dati di salute",
                            style = MaterialTheme.typography.headlineSmall,
                            color = AccantoColors.Ink,
                        )
                        Section(
                            "Cosa legge",
                            "Solo frequenza cardiaca e passi, scritti dal tuo orologio tramite " +
                                "Mi Fitness. Nient'altro: non il sonno, non la posizione, non " +
                                "gli allenamenti.",
                        )
                        Section(
                            "A cosa serve",
                            "A far sapere a chi hai autorizzato che stai bene. Un battito " +
                                "recente dice che l'orologio è al polso e che stai bene; " +
                                "l'assenza di dati per ore è ciò che fa capire che qualcosa " +
                                "merita un controllo.",
                        )
                        Section(
                            "Chi lo vede",
                            "Solo le persone a cui tu hai dato il permesso, e solo quelle " +
                                "metriche che hai concesso. Puoi revocare in qualsiasi momento, " +
                                "e ogni accesso resta registrato dove puoi consultarlo.",
                        )
                        Section(
                            "Cosa non facciamo",
                            "I dati non vengono venduti né condivisi con terzi, e non escono " +
                                "dal server che hai scelto tu.",
                        )
                    }
                }
            }
        }
    }
}

@androidx.compose.runtime.Composable
private fun Section(title: String, body: String) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(title, style = MaterialTheme.typography.titleSmall, color = AccantoColors.Ink)
        Text(body, style = MaterialTheme.typography.bodyMedium, color = AccantoColors.InkSecondary)
    }
}
