package ar.elroso.domotica.tele.core

/** Lo que la app le hace al equipo; lo implementa Android. */
interface TeleDevice {
    /** Si la pantalla está prendida. */
    val interactive: Boolean
    /** El volumen del stream de música, en pasos. */
    val volume: Int
    val maxVolume: Int

    /** Prende la tele. */
    fun wake()

    fun setVolume(index: Int)

    /** Reproduce el audio y espera a que termine; false si no se pudo bajar o reproducir. */
    fun play(url: String, seconds: Double?): Boolean

    /** Corta el audio que esté sonando. */
    fun stopAudio()

    /** Pone adelante la vista con esa página. */
    fun show(url: String)

    /** Vuelve la vista al kiosco. */
    fun kiosk()

    /** Vuelve al kiosco y deja de estar adelante. */
    fun hide()
}

/** Ejecuta cada orden del CT y contesta su `ack`. */
class OrderRunner(
    private val device: TeleDevice,
    private val ack: (Long, AckState) -> Unit,
    private val log: (String) -> Unit,
    private val sleep: (Long) -> Unit = Thread::sleep,
    private val now: () -> Long = System::currentTimeMillis,
    private val wakeTimeoutMs: Long = 10_000,
    private val settleMs: Long = 20_000,
    private val pollMs: Long = 250,
    private val keep: Int = 64,
) {
    // El último estado contestado de cada orden, para repetirlo si el CT no lo recibió.
    private val answered = LinkedHashMap<Long, AckState>()

    // Crece con cada `stop`: un `play` que la ve cambiar se corta.
    @Volatile
    private var stops = 0

    fun run(order: Order) {
        answer(order.seq, AckState.RECEIVED)
        when (order.kind) {
            OrderKind.PLAY -> play(order)
            OrderKind.SHOW -> show(order)
            OrderKind.STOP -> {
                stops++
                device.stopAudio()
                device.kiosk()
            }
            OrderKind.HIDE -> device.hide()
        }
    }

    /** Repite lo ya contestado de una orden que el CT volvió a mandar, sin ejecutarla de nuevo. */
    fun resend(order: Order) {
        val last = synchronized(answered) { answered[order.seq] }
        ack(order.seq, AckState.RECEIVED)
        if (last != null && last != AckState.RECEIVED) ack(order.seq, last)
    }

    private fun answer(seq: Long, state: AckState) {
        synchronized(answered) {
            answered[seq] = state
            while (answered.size > keep) answered.remove(answered.keys.first())
        }
        ack(seq, state)
    }

    private fun show(order: Order) {
        val url = order.url ?: return fail(order, "orden show sin url")
        device.wake()
        device.show(url)
    }

    private fun play(order: Order) {
        val url = order.url ?: return fail(order, "orden play sin url")
        val generation = stops
        val asleep = !device.interactive
        device.wake()
        val start = now()
        while (!device.interactive && now() - start < wakeTimeoutMs) {
            sleep(pollMs)
            if (stops != generation) return log("play ${order.seq} cortado antes de sonar")
        }
        if (!device.interactive) log("la tele no prendió en ${wakeTimeoutMs / 1000} s; suena igual")
        if (asleep) sleep(settleMs)
        if (stops != generation) return log("play ${order.seq} cortado antes de sonar")

        val previous = device.volume
        val floor = VolumeFloor.index(order.minVolume, device.maxVolume)
        if (previous < floor) {
            log("subo el volumen de $previous a $floor")
            device.setVolume(floor)
        }
        val played = try {
            device.play(url, order.seconds)
        } finally {
            if (previous < floor) device.setVolume(previous)
        }
        when {
            stops != generation -> log("play ${order.seq} cortado mientras sonaba")
            played -> answer(order.seq, AckState.DONE)
            else -> fail(order, "no pude reproducir el audio")
        }
    }

    private fun fail(order: Order, reason: String) {
        log("orden ${order.seq} fallida: $reason")
        answer(order.seq, AckState.FAILED)
    }
}
