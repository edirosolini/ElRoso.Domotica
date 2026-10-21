package ar.elroso.domotica.tele

import android.content.Context
import android.provider.Settings
import android.util.Log
import ar.elroso.domotica.tele.core.AppVersion
import ar.elroso.domotica.tele.core.Caps
import ar.elroso.domotica.tele.core.Offer
import ar.elroso.domotica.tele.core.OfferLog
import ar.elroso.domotica.tele.core.TeleApi
import ar.elroso.domotica.tele.core.TeleChoice
import ar.elroso.domotica.tele.core.TeleUrls

/** Lo compartido por las pantallas, el servicio y el arranque: registro, elección y API. */
object Tele {
    private const val TAG = "DomoticaTele"
    private const val PREFS = "tele"
    private const val KEY_ALIAS = "alias"
    private const val KEY_CHAT = "chat_id"
    private const val KEY_PERSON = "person_id"
    private const val KEY_OFFER_CODE = "offer_code"
    private const val KEY_OFFER_AT = "offer_at"
    private const val KEY_REJECTED = "rejected_code"

    val urls = TeleUrls(BuildConfig.HOUSE_URL)
    val transport = HttpTransport()
    val api = TeleApi(transport, urls)
    val version = AppVersion(BuildConfig.VERSION_NAME, BuildConfig.VERSION_CODE)

    fun log(event: String) {
        Log.i(TAG, event)
    }

    fun choice(context: Context): TeleChoice {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val chat = if (prefs.contains(KEY_CHAT)) prefs.getLong(KEY_CHAT, 0) else null
        val person = if (prefs.contains(KEY_PERSON)) prefs.getLong(KEY_PERSON, 0) else null
        return TeleChoice(prefs.getString(KEY_ALIAS, null), chat, person)
    }

    fun save(context: Context, choice: TeleChoice) {
        val editor = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
        editor.putString(KEY_ALIAS, choice.alias)
        val chat = choice.chatId
        if (chat == null) editor.remove(KEY_CHAT) else editor.putLong(KEY_CHAT, chat)
        val person = choice.personId
        if (person == null) editor.remove(KEY_PERSON) else editor.putLong(KEY_PERSON, person)
        editor.apply()
    }

    /** Lo que la app sabe hacer hoy en este equipo. */
    fun caps(context: Context): List<String> = Caps.of(overlay = Settings.canDrawOverlays(context))

    /** Si el sistema deja a la app pedir instalar paquetes. */
    fun canInstall(context: Context): Boolean = context.packageManager.canRequestPackageInstalls()

    /** La última versión ofrecida para instalar, guardada en `SharedPreferences`. */
    fun offers(context: Context): OfferLog = object : OfferLog {
        private val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

        override fun last(): Offer? =
            if (prefs.contains(KEY_OFFER_CODE)) Offer(prefs.getInt(KEY_OFFER_CODE, 0), prefs.getLong(KEY_OFFER_AT, 0)) else null

        override fun save(offer: Offer) {
            prefs.edit().putInt(KEY_OFFER_CODE, offer.versionCode).putLong(KEY_OFFER_AT, offer.at).apply()
        }

        override fun rejected(): Int? = if (prefs.contains(KEY_REJECTED)) prefs.getInt(KEY_REJECTED, 0) else null

        override fun reject(versionCode: Int) {
            prefs.edit().putInt(KEY_REJECTED, versionCode).apply()
        }
    }
}
