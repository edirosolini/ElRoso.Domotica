package ar.elroso.domotica.tele.core

/** Cada cuánto late la tele: fijo mientras anda, duplicándose hasta un tope sin red. */
class BeatSchedule(private val baseMs: Long = 5_000, private val maxMs: Long = 60_000) {
    var delay: Long = baseMs
        private set

    /** Vuelve al ritmo base y lo devuelve. */
    fun succeeded(): Long {
        delay = baseMs
        return delay
    }

    /** Duplica la espera hasta el tope y la devuelve. */
    fun failed(): Long {
        delay = minOf(delay * 2, maxMs)
        return delay
    }
}
