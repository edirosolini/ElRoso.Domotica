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
    data class Alarm(val id: Long?) : PollResult
    data object NotRegistered : PollResult
    data class Failed(val reason: String) : PollResult
}

/** Las tres rutas de la tele en el CT. */
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
            200 -> PollResult.Alarm(parse({ Protocol.parsePoll(reply.body).alarm }) { return PollResult.Failed(it) })
            404 -> PollResult.NotRegistered
            else -> PollResult.Failed(describe(reply))
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
