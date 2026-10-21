package ar.elroso.domotica.tele.core

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.SerializationException
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.longOrNull
import kotlinx.serialization.json.put

/** Una persona de la casa, como la manda `setup`. */
@Serializable
data class Person(@SerialName("chat_id") val chatId: Long, val name: String)

/** Con qué se configura la app: las teles con pantalla y la gente de la casa. */
@Serializable
data class Setup(val devices: List<String> = emptyList(), val people: List<Person> = emptyList())

/** El registro de la tele que se manda en `hello`. */
@Serializable
data class Hello(
    val alias: String,
    @SerialName("version_name") val versionName: String,
    @SerialName("version_code") val versionCode: Int,
    val caps: List<String>,
)

/** Lo que el CT aceptó del registro. */
@Serializable
data class HelloReply(val alias: String, val caps: List<String> = emptyList())

/** Lo que el CT le pide a la tele. */
@Serializable
enum class OrderKind {
    @SerialName("play") PLAY,
    @SerialName("show") SHOW,
    @SerialName("stop") STOP,
    @SerialName("hide") HIDE,
}

/** Una orden del buzón: `play` trae `url`, `minVolume` (0 a 100) y `seconds`; `show`, `url`. */
@Serializable
data class Order(
    val seq: Long,
    val kind: OrderKind,
    val url: String? = null,
    @SerialName("min_volume") val minVolume: Int? = null,
    val seconds: Double? = null,
)

/** Lo que la app contesta de una orden. */
enum class AckState(val wire: String) {
    RECEIVED("received"),
    DONE("done"),
    FAILED("failed"),
}

/** La respuesta de `poll`: la alarma que suena en la tele, o null, y las órdenes pendientes. */
data class PollReply(val alarm: Long? = null, val orders: List<Order> = emptyList())

@Serializable
private data class AckReply(val accepted: Boolean = false)

@Serializable
private data class CommandReply(val text: String = "")

/** Parseo y armado del JSON del contrato con el CT. */
object Protocol {
    private val json = Json { ignoreUnknownKeys = true }

    fun parseSetup(body: String): Setup = json.decodeFromString(Setup.serializer(), body)

    fun encodeHello(hello: Hello): String = json.encodeToString(Hello.serializer(), hello)

    fun parseHelloReply(body: String): HelloReply = json.decodeFromString(HelloReply.serializer(), body)

    /** Lee el `poll`; una orden ilegible o de un tipo desconocido se descarta. */
    fun parsePoll(body: String): PollReply {
        val root = json.parseToJsonElement(body) as? JsonObject ?: throw SerializationException("poll sin objeto")
        val alarm = (root["alarm"] as? JsonPrimitive)?.longOrNull
        val orders = (root["orders"] as? JsonArray).orEmpty().mapNotNull {
            try {
                json.decodeFromJsonElement(Order.serializer(), it)
            } catch (e: SerializationException) {
                null
            } catch (e: IllegalArgumentException) {
                null
            }
        }
        return PollReply(alarm, orders)
    }

    fun encodeAck(seq: Long, state: AckState): String = buildJsonObject {
        put("seq", seq)
        put("state", state.wire)
    }.toString()

    fun parseAck(body: String): Boolean = json.decodeFromString(AckReply.serializer(), body).accepted

    fun encodeCommand(chatId: Long, data: String): String = buildJsonObject {
        put("chat_id", chatId)
        put("data", data)
    }.toString()

    fun parseCommand(body: String): String = json.decodeFromString(CommandReply.serializer(), body).text

    /** El campo `error` de una respuesta del CT, o null si no lo trae. */
    fun parseError(body: String): String? = try {
        ((json.parseToJsonElement(body) as? JsonObject)?.get("error") as? JsonPrimitive)?.contentOrNull
    } catch (e: SerializationException) {
        null
    }
}
