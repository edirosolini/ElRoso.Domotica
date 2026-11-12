package ar.elroso.domotica.tele.core

/** Qué hace la tecla OK del kiosco: con alarma la apaga al soltar; sin alarma, mantenida tres segundos abre el cambio de tele o persona. */
class OkKey(private val holdMs: Long = HOLD_MS) {

    companion object {
        const val HOLD_MS = 3_000L
    }

    enum class Action { NONE, SILENCE, CHANGE }

    private var downAt: Long? = null
    private var fired = false

    /** Una pulsación o su repetición, con la hora del evento en milisegundos. */
    fun down(now: Long, repeat: Boolean, alarm: Boolean): Action {
        if (!repeat || downAt == null) {
            downAt = now
            fired = false
            return Action.NONE
        }
        return change(now, alarm)
    }

    /** Al soltar: con alarma apaga; sin ella, abre el cambio si se mantuvo y todavía no se abrió. */
    fun up(now: Long, alarm: Boolean): Action {
        val action = if (alarm) Action.SILENCE else change(now, alarm)
        downAt = null
        fired = false
        return action
    }

    private fun change(now: Long, alarm: Boolean): Action {
        val start = downAt ?: return Action.NONE
        if (alarm || fired || now - start < holdMs) return Action.NONE
        fired = true
        return Action.CHANGE
    }
}
