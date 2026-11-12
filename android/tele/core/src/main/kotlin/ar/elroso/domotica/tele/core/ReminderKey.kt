package ar.elroso.domotica.tele.core

/** Una tecla del control, como la ve el cartel del recordatorio. */
enum class Remote { OK, BACK, OTHER }

/** Qué hace cada tecla del control sobre el cartel de un recordatorio. */
object ReminderKey {

    enum class Action { DONE, LATER, CLOSE, NONE }

    /** Con persona elegida, OK marca hecho y Atrás lo deja para más tarde; sin persona, los dos cierran; otra tecla, nada. */
    fun action(key: Remote, caller: Caller?): Action = when (key) {
        Remote.OK -> if (caller == null) Action.CLOSE else Action.DONE
        Remote.BACK -> if (caller == null) Action.CLOSE else Action.LATER
        Remote.OTHER -> Action.NONE
    }

    /** El comando que marca hecho el recordatorio a nombre de quien se eligió; null sin nadie elegido. */
    fun doneCommand(reminder: Reminder, caller: Caller?): String? =
        if (caller == null) null else "hecho ${reminder.id}"
}
