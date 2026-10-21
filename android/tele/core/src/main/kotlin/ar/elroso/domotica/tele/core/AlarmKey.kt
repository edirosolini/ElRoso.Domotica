package ar.elroso.domotica.tele.core

/** Qué hace la tecla OK del control mientras suena una alarma. */
object AlarmKey {
    /** El botón que apaga la alarma a nombre de la persona; null sin alarma o sin persona. */
    fun offCommand(alarm: Long?, chatId: Long?): String? =
        if (alarm == null || chatId == null) null else "callar $alarm"
}
