package ar.elroso.domotica.tele.core

import kotlinx.serialization.SerializationException
import java.io.IOException

/** Una respuesta HTTP: código y cuerpo. */
data class HttpReply(val status: Int, val body: String)

/** Cómo se habla con el CT; lanza IOException si no hay red. */
interface Transport {
    @Throws(IOException::class)
    fun get(url: String): HttpReply

    @Throws(IOException::class)
    fun postJson(url: String, body: String): HttpReply
}

/** El pedido no se pudo completar, con el motivo. */
class TeleFailure(message: String) : Exception(message)

/** Cómo terminó un `hello`. */
sealed interface HelloResult {
    data class Accepted(val caps: List<String>) : HelloResult
    data class Rejected(val status: Int, val reason: String) : HelloResult
    data class Failed(val reason: String) : HelloResult
}

/** Cómo terminó un `poll`. */
sealed interface PollResult {
    data class Alarm(val id: Long?, val orders: List<Order> = emptyList()) : PollResult
    data object NotRegistered : PollResult
    data class Failed(val reason: String) : PollResult
}

/** Cómo terminó un `ack`: si el CT lo aceptó, o por qué no llegó. */
sealed interface AckResult {
    data class Answered(val accepted: Boolean) : AckResult
    data class Failed(val reason: String) : AckResult
}

/** Cómo terminó un comando: la respuesta del CT, o por qué no. */
sealed interface CommandResult {
    data class Replied(val text: String) : CommandResult
    data class Failed(val reason: String) : CommandResult
}

/** Cómo terminó la consulta de `tele.json`. */
sealed interface ReleaseResult {
    data class Published(val release: Release) : ReleaseResult
    data object Unpublished : ReleaseResult
    data class Failed(val reason: String) : ReleaseResult
}

/** Las rutas de la tele en el CT y el comando de la pantalla de control. */
class TeleApi(private val transport: Transport, private val urls: TeleUrls) {

    /** Lo necesario para el primer uso; lanza TeleFailure si no se pudo. */
    fun setup(): Setup {
        val reply = send({ transport.get(urls.setup) }) { throw TeleFailure(it) }
        if (reply.status != 200) throw TeleFailure(describe(reply))
        return parse({ Protocol.parseSetup(reply.body) }) { throw TeleFailure(it) }
    }

    fun hello(hello: Hello): HelloResult {
        val reply = send({ transport.postJson(urls.hello, Protocol.encodeHello(hello)) }) {
            return HelloResult.Failed(it)
        }
        return when (reply.status) {
            200 -> HelloResult.Accepted(parse({ Protocol.parseHelloReply(reply.body).caps }) { return HelloResult.Failed(it) })
            in 400..499 -> HelloResult.Rejected(reply.status, Protocol.parseError(reply.body) ?: "")
            else -> HelloResult.Failed(describe(reply))
        }
    }

    fun poll(alias: String): PollResult {
        val reply = send({ transport.get(urls.poll(alias)) }) { return PollResult.Failed(it) }
        return when (reply.status) {
            200 -> {
                val poll = parse({ Protocol.parsePoll(reply.body) }) { return PollResult.Failed(it) }
                PollResult.Alarm(poll.alarm, poll.orders)
            }
            404 -> PollResult.NotRegistered
            else -> PollResult.Failed(describe(reply))
        }
    }

    fun ack(alias: String, seq: Long, state: AckState): AckResult {
        val reply = send({ transport.postJson(urls.ack(alias), Protocol.encodeAck(seq, state)) }) {
            return AckResult.Failed(it)
        }
        if (reply.status != 200) return AckResult.Failed(describe(reply))
        return AckResult.Answered(parse({ Protocol.parseAck(reply.body) }) { return AckResult.Failed(it) })
    }

    /** Corre un comando de botón (`data`) a nombre de esa persona o ese chat, como la pantalla de control. */
    fun command(caller: Caller, data: String): CommandResult {
        val reply = send({ transport.postJson(urls.command, Protocol.encodeCommand(caller, data)) }) {
            return CommandResult.Failed(it)
        }
        if (reply.status != 200) return CommandResult.Failed(describe(reply))
        return CommandResult.Replied(parse({ Protocol.parseCommand(reply.body) }) { return CommandResult.Failed(it) })
    }

    /** La versión de la app publicada en el CT. */
    fun release(): ReleaseResult {
        val reply = send({ transport.get(urls.release) }) { return ReleaseResult.Failed(it) }
        return when (reply.status) {
            200 -> Protocol.parseRelease(reply.body)?.let { ReleaseResult.Published(it) }
                ?: ReleaseResult.Failed("tele.json inválido")
            404 -> ReleaseResult.Unpublished
            else -> ReleaseResult.Failed(describe(reply))
        }
    }

    private inline fun send(request: () -> HttpReply, onFailure: (String) -> Nothing): HttpReply = try {
        request()
    } catch (e: IOException) {
        onFailure(e.message ?: e.javaClass.simpleName)
    }

    private inline fun <T> parse(read: () -> T, onFailure: (String) -> Nothing): T = try {
        read()
    } catch (e: SerializationException) {
        onFailure("respuesta ilegible del CT")
    }

    private fun describe(reply: HttpReply): String {
        val error = Protocol.parseError(reply.body)
        return if (error == null) "HTTP ${reply.status}" else "HTTP ${reply.status}: $error"
    }
}
