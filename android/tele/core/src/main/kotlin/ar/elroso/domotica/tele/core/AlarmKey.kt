package ar.elroso.domotica.tele.core

/** Qué hace la tecla OK del control mientras suena una alarma. */
object AlarmKey {
    /** El botón que apaga la alarma a nombre de quien se eligió; null sin alarma o sin nadie elegido. */
    fun offCommand(alarm: Long?, caller: Caller?): String? =
        if (alarm == null || caller == null) null else "callar $alarm"
}
