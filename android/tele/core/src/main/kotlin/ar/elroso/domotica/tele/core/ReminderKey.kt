package ar.elroso.domotica.tele.core

/** Qué hace la tecla OK del control sobre el cartel de un recordatorio. */
object ReminderKey {
    /** El comando que marca hecho el recordatorio a nombre de quien se eligió; null sin nadie elegido. */
    fun doneCommand(reminder: Reminder, caller: Caller?): String? =
        if (caller == null) null else "hecho ${reminder.id}"
}
