package ar.elroso.domotica.tele

import android.content.Context
import android.provider.Settings
import android.util.Log
import ar.elroso.domotica.tele.core.AppVersion
import ar.elroso.domotica.tele.core.Caps
import ar.elroso.domotica.tele.core.TeleApi
import ar.elroso.domotica.tele.core.TeleChoice
import ar.elroso.domotica.tele.core.TeleUrls

/** Lo compartido por las pantallas, el servicio y el arranque: registro, elección y API. */
object Tele {
    private const val TAG = "DomoticaTele"
    private const val PREFS = "tele"
    private const val KEY_ALIAS = "alias"
    private const val KEY_CHAT = "chat_id"

    val urls = TeleUrls(BuildConfig.HOUSE_URL)
    val api = TeleApi(HttpTransport(), urls)
    val version = AppVersion(BuildConfig.VERSION_NAME, BuildConfig.VERSION_CODE)

    fun log(event: String) {
        Log.i(TAG, event)
    }

    fun choice(context: Context): TeleChoice {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val chat = if (prefs.contains(KEY_CHAT)) prefs.getLong(KEY_CHAT, 0) else null
        return TeleChoice(prefs.getString(KEY_ALIAS, null), chat)
    }

    fun save(context: Context, choice: TeleChoice) {
        val editor = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
        editor.putString(KEY_ALIAS, choice.alias)
        val chat = choice.chatId
        if (chat == null) editor.remove(KEY_CHAT) else editor.putLong(KEY_CHAT, chat)
        editor.apply()
    }

    /** Lo que la app sabe hacer hoy en este equipo. */
    fun caps(context: Context): List<String> = Caps.of(overlay = Settings.canDrawOverlays(context))
}
