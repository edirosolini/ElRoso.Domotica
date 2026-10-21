package ar.elroso.domotica.tele.core

/** A nombre de quién se corre un comando: una persona del padrón o un chat. */
sealed interface Caller {
    data class Person(val id: Long) : Caller
    data class Chat(val id: Long) : Caller
}

/** Lo elegido al configurar: qué tele es y de quién; una elección vieja trae solo el chat. */
data class TeleChoice(val alias: String?, val chatId: Long?, val personId: Long? = null) {
    val ready: Boolean get() = !alias.isNullOrBlank()

    /** A nombre de quién apaga el OK: la persona si hay, si no el chat. */
    val caller: Caller?
        get() = personId?.let { Caller.Person(it) } ?: chatId?.let { Caller.Chat(it) }

    companion object {
        fun of(alias: String, caller: Caller?): TeleChoice = when (caller) {
            is Caller.Person -> TeleChoice(alias, chatId = null, personId = caller.id)
            is Caller.Chat -> TeleChoice(alias, chatId = caller.id)
            null -> TeleChoice(alias, chatId = null)
        }
    }
}

/** Una opción de «¿de quién es la tele?»: lo que se muestra y a nombre de quién queda. */
data class Owner(val label: String, val caller: Caller)

/** Las opciones de dueño que da `setup`. */
object Owners {
    /** Las personas del padrón; con el padrón vacío, los chats de la casa. */
    fun of(setup: Setup): List<Owner> =
        if (setup.persons.isNotEmpty()) {
            setup.persons.map { Owner(if (it.chatId == null) "${it.name} (sin Telegram)" else it.name, Caller.Person(it.id)) }
        } else {
            setup.people.map { Owner(it.name, Caller.Chat(it.chatId)) }
        }
}

/** Las capacidades que la app anuncia en `hello`. */
object Caps {
    const val PLAY = "play"
    const val SHOW = "show"
    const val OVERLAY = "overlay"

    /** Las capacidades de la tele: `play` siempre; `show` y `overlay` solo con la superposición. */
    fun of(overlay: Boolean): List<String> = if (overlay) listOf(PLAY, SHOW, OVERLAY) else listOf(PLAY)
}
