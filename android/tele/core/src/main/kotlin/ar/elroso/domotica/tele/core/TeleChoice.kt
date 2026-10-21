package ar.elroso.domotica.tele.core

/** Lo elegido en el primer uso: qué tele es y de quién. */
data class TeleChoice(val alias: String?, val chatId: Long?) {
    val ready: Boolean get() = !alias.isNullOrBlank()
}

/** Las capacidades que la app anuncia en `hello`. */
object Caps {
    const val OVERLAY = "overlay"

    fun of(overlay: Boolean): List<String> = if (overlay) listOf(OVERLAY) else emptyList()
}
