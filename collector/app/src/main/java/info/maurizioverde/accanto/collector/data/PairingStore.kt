package info.maurizioverde.accanto.collector.data

import android.content.Context
import androidx.core.content.edit
import info.maurizioverde.accanto.collector.BuildConfig

/**
 * Where the device credential lives.
 *
 * Plain SharedPreferences on purpose. `EncryptedSharedPreferences` would add a
 * comforting name without much substance here: the file already sits in
 * app-private storage, and anyone able to read it has root, at which point the
 * key material is equally reachable. What actually protects this credential is
 * that it is revocable server-side, excluded from backups and from
 * device-to-device transfer.
 */
class PairingStore(context: Context) {

    private val prefs = context.getSharedPreferences("accanto.pairing", Context.MODE_PRIVATE)

    var apiUrl: String
        get() = prefs.getString(KEY_API_URL, null) ?: BuildConfig.DEFAULT_API_URL
        set(value) = prefs.edit { putString(KEY_API_URL, value.trimEnd('/')) }

    var deviceToken: String?
        get() = prefs.getString(KEY_TOKEN, null)
        set(value) = prefs.edit { putString(KEY_TOKEN, value) }

    var subjectId: String?
        get() = prefs.getString(KEY_SUBJECT, null)
        set(value) = prefs.edit { putString(KEY_SUBJECT, value) }

    val isPaired: Boolean
        get() = !deviceToken.isNullOrBlank() && !subjectId.isNullOrBlank()

    fun clear() = prefs.edit { clear() }

    private companion object {
        const val KEY_API_URL = "api_url"
        const val KEY_TOKEN = "device_token"
        const val KEY_SUBJECT = "subject_id"
    }
}
