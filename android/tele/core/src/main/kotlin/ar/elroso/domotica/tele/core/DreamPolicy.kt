package ar.elroso.domotica.tele.core

/** Si el protector de pantalla sigue o se corta, y por qué. */
enum class DreamDecision {
    KEEP,
    ALARM,
    REMINDER,
    QUIET,
}

/** Decide si el kiosco sigue como protector de pantalla. */
object DreamPolicy {
    fun decide(alarm: Long?, reminder: Boolean, quiet: Boolean): DreamDecision = when {
        alarm != null -> DreamDecision.ALARM
        reminder -> DreamDecision.REMINDER
        quiet -> DreamDecision.QUIET
        else -> DreamDecision.KEEP
    }
}
