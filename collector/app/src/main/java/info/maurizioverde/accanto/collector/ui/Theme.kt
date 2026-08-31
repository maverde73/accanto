package info.maurizioverde.accanto.collector.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

/** Tokens from design/accanto-mobile.dc.html, plus the derived state tones. */
object AccantoColors {
    val Background = Color(0xFFF7F5F1)
    val Surface = Color(0xFFFFFFFF)
    val Ink = Color(0xFF232A26)
    val InkSecondary = Color(0xFF5C584D)
    val InkMuted = Color(0xFF8A8578)
    val InkFaint = Color(0xFF9B9686)

    /** Activity: interaction or movement, recently observed. */
    val Green = Color(0xFF4A6B5C)

    /** Known but quiet. Never used for a broken pipeline. */
    val Amber = Color(0xFFA8763A)

    /** "I don't know" -- absent data, which is not an alarm. */
    val Grey = Color(0xFF9B9686)

    /** Reserved for the positive presence of a problem. */
    val Red = Color(0xFFA4503F)
}

private val AccantoColorScheme = lightColorScheme(
    primary = AccantoColors.Green,
    onPrimary = Color.White,
    background = AccantoColors.Background,
    onBackground = AccantoColors.Ink,
    surface = AccantoColors.Surface,
    onSurface = AccantoColors.Ink,
    error = AccantoColors.Red,
)

@Composable
fun AccantoTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = AccantoColorScheme, content = content)
}
