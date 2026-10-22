package ar.elroso.domotica.tele.core

/** Qué recordatorio va en el cartel de la tele, uno por vez; no es seguro entre hilos. */
class ReminderBoard {
    private var reminders: List<Reminder> = emptyList()
    private var alarm: Long? = null
    // Los cerrados con otra tecla, con los re-avisos que llevaban al cerrarse.
    private val dismissed = mutableMapOf<Long, Int>()
    // Los marcados hecho desde la tele.
    private val done = mutableSetOf<Long>()

    /** El recordatorio a mostrar: el más viejo que no se cerró ni se marcó; null con alarma o sin ninguno. */
    val card: Reminder?
        get() = if (alarm != null) {
            null
        } else {
            reminders.filter { it.id !in done && (dismissed[it.id] ?: -1) < it.nags }.minByOrNull { it.id }
        }

    /** Anota la lista del `poll` y olvida lo cerrado o marcado que ya no trae. */
    fun reminders(list: List<Reminder>) {
        reminders = list
        val ids = list.map { it.id }.toSet()
        dismissed.keys.retainAll(ids)
        done.retainAll(ids)
    }

    fun alarm(id: Long?) {
        alarm = id
    }

    /** Cierra el cartel hasta el próximo re-aviso de ese recordatorio. */
    fun dismiss(reminder: Reminder) {
        dismissed[reminder.id] = reminder.nags
    }

    /** No vuelve a mostrar ese recordatorio mientras el `poll` lo siga trayendo. */
    fun done(id: Long) {
        done += id
    }
}
