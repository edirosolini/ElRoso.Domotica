package ar.elroso.domotica.tele.core

/** El piso de volumen del CT, de 0 a 100, llevado a los pasos del stream de la tele. */
object VolumeFloor {
    private const val DEFAULT_PERCENT = 50

    /** El paso mínimo para ese porcentaje, redondeado hacia arriba; sin porcentaje, la mitad. */
    fun index(minVolume: Int?, max: Int): Int {
        if (max <= 0) return 0
        val percent = (minVolume ?: DEFAULT_PERCENT).coerceIn(0, 100)
        return ((percent * max + 99) / 100).coerceIn(0, max)
    }
}
