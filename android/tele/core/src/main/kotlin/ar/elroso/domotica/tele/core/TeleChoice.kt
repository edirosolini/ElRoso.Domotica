package ar.elroso.domotica.tele.core

/** Lo elegido en el primer uso: qué tele es y de quién. */
data class TeleChoice(val alias: String?, val chatId: Long?) {
    val ready: Boolean get() = !alias.isNullOrBlank()
}

/** Las capacidades que la app anuncia en `hello`. */
object Caps {
    const val PLAY = "play"
    const val SHOW = "show"
    const val OVERLAY = "overlay"

    /** Las capacidades de la tele: `play` siempre; `show` y `overlay` solo con la superposición. */
    fun of(overlay: Boolean): List<String> = if (overlay) listOf(PLAY, SHOW, OVERLAY) else listOf(PLAY)
}
