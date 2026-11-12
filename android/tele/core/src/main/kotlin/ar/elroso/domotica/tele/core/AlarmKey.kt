package ar.elroso.domotica.tele.core

/** Qué hace la tecla OK del control mientras suena una alarma, y qué alarma ya se apagó desde la tele. */
class AlarmKey {

    companion object {
        /** Cuánto queda «🔕 Alarma apagada» abajo. */
        const val SILENCED_MS = 2_000L

        /** El comando que apaga la alarma a nombre de quien se eligió; null sin alarma o sin nadie elegido. */
        fun offCommand(alarm: Long?, caller: Caller?): String? =
            if (alarm == null || caller == null) null else "callar $alarm"
    }

    private var alarm: Long? = null
    private var sending: Long? = null
    private var off: Long? = null

    /** Si la alarma que suena ya se apagó desde esta tele. */
    val silenced: Boolean
        get() = alarm != null && alarm == off

    /** Anota la alarma del `poll`; la apagada se olvida cuando deja de venir. */
    fun alarm(id: Long?) {
        alarm = id
        if (off != id) off = null
        if (sending != id) sending = null
    }

    /** El comando de este OK; null sin alarma, sin nadie elegido, esperando respuesta o ya apagada. */
    fun press(caller: Caller?): String? {
        val id = alarm ?: return null
        if (sending == id || off == id) return null
        val command = offCommand(id, caller) ?: return null
        sending = id
        return command
    }

    /** Anota cómo terminó el OK: si el CT contestó, la alarma queda apagada; si no, se puede reintentar. */
    fun answered(id: Long, replied: Boolean) {
        if (sending == id) sending = null
        if (replied && alarm == id) off = id
    }
}
