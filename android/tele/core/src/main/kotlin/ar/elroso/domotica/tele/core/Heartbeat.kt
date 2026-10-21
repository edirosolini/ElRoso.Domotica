package ar.elroso.domotica.tele.core

/** La versión de la app que se anuncia en `hello`. */
data class AppVersion(val name: String, val code: Int)

/** El latido de la tele: se registra, consulta la alarma y dice cuándo volver a latir. */
class Heartbeat private constructor(
    private val alias: String,
    private val api: TeleApi,
    private val version: AppVersion,
    private val caps: () -> List<String>,
    private val log: (String) -> Unit,
    private val schedule: BeatSchedule,
    private val onAlarm: (Long?) -> Unit,
    private val onOrders: (List<Order>) -> Unit,
    private val onRepeated: (List<Order>) -> Unit,
) {
    companion object {
        /** Arma el latido de esa elección, o null si todavía no tiene tele. */
        fun forChoice(
            choice: TeleChoice,
            api: TeleApi,
            version: AppVersion,
            caps: () -> List<String>,
            log: (String) -> Unit,
            schedule: BeatSchedule = BeatSchedule(),
            onAlarm: (Long?) -> Unit = {},
            onOrders: (List<Order>) -> Unit = {},
            onRepeated: (List<Order>) -> Unit = {},
        ): Heartbeat? {
            val alias = choice.alias?.takeIf { choice.ready } ?: return null
            return Heartbeat(alias, api, version, caps, log, schedule, onAlarm, onOrders, onRepeated)
        }
    }

    // Las capacidades que el CT ya tiene registradas; null si hay que saludar.
    private var announced: List<String>? = null
    private var alarm: Long? = null
    private val inbox = OrderInbox()

    /** Saluda si hace falta, si no consulta la alarma; devuelve los milisegundos hasta el próximo latido. */
    fun tick(): Long {
        val current = caps()
        return if (announced != current) hello(current) else poll()
    }

    private fun hello(current: List<String>): Long =
        when (val result = api.hello(Hello(alias, version.name, version.code, current))) {
            is HelloResult.Accepted -> {
                announced = current
                log("registrada como $alias, capacidades aceptadas: ${result.caps}")
                schedule.succeeded()
            }
            is HelloResult.Rejected -> {
                log("el CT rechazó el registro (${result.status}): ${result.reason}")
                schedule.failed()
            }
            is HelloResult.Failed -> unreachable(result.reason)
        }

    private fun poll(): Long = when (val result = api.poll(alias)) {
        is PollResult.Alarm -> {
            if (result.id != alarm) {
                alarm = result.id
                log(if (result.id == null) "la tele ya no tiene alarma" else "alarma en la tele: ${result.id}")
                onAlarm(result.id)
            }
            val sorted = inbox.sort(result.orders)
            if (sorted.repeated.isNotEmpty()) onRepeated(sorted.repeated)
            if (sorted.fresh.isNotEmpty()) onOrders(sorted.fresh)
            schedule.succeeded()
        }
        PollResult.NotRegistered -> {
            announced = null
            log("el CT no conoce la tele; vuelve a registrarse")
            schedule.succeeded()
        }
        is PollResult.Failed -> unreachable(result.reason)
    }

    private fun unreachable(reason: String): Long {
        val delay = schedule.failed()
        log("sin contacto con el CT ($reason); reintento en ${delay / 1000} s")
        return delay
    }
}
