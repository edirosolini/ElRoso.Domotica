package ar.elroso.domotica.tele.core

import kotlinx.serialization.KSerializer
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.SerializationException
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.longOrNull
import kotlinx.serialization.json.put

/** Una persona de la casa, como la manda `setup`. */
@Serializable
data class Person(@SerialName("chat_id") val chatId: Long, val name: String)

/** Una persona del padrón, con su chat o sin Telegram. */
@Serializable
data class Resident(val id: Long, val name: String, @SerialName("chat_id") val chatId: Long? = null)

/** Con qué se configura la app: las teles con pantalla, los chats y el padrón de la casa. */
@Serializable
data class Setup(
    val devices: List<String> = emptyList(),
    val people: List<Person> = emptyList(),
    val persons: List<Resident> = emptyList(),
)

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

/** Un recordatorio que sonó y espera su «Hecho»: para quién es, si se sabe, y cuántos re-avisos lleva. */
@Serializable
data class Reminder(
    val id: Long,
    val message: String,
    @SerialName("for") val forName: String? = null,
    val nags: Int = 0,
)

/** Lo que la app contesta de una orden. */
enum class AckState(val wire: String) {
    RECEIVED("received"),
    DONE("done"),
    FAILED("failed"),
}

/** La respuesta de `poll`: la alarma que suena en la tele, o null, las órdenes pendientes, los recordatorios y si la casa está callada. */
data class PollReply(
    val alarm: Long? = null,
    val orders: List<Order> = emptyList(),
    val reminders: List<Reminder> = emptyList(),
    val quiet: Boolean = false,
)

/** La versión publicada en `tele.json`, con el sha256 en minúsculas y el tamaño en bytes. */
data class Release(val versionCode: Int, val versionName: String, val sha256: String, val size: Long)

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

    /** Lee el `poll`; una orden o un recordatorio ilegible, o una orden de un tipo desconocido, se descarta, y `quiet` ausente o ilegible es false. */
    fun parsePoll(body: String): PollReply {
        val root = json.parseToJsonElement(body) as? JsonObject ?: throw SerializationException("poll sin objeto")
        val alarm = (root["alarm"] as? JsonPrimitive)?.longOrNull
        val quiet = (root["quiet"] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull ?: false
        return PollReply(alarm, root.items("orders", Order.serializer()), root.items("reminders", Reminder.serializer()), quiet)
    }

    private fun <T> JsonObject.items(key: String, serializer: KSerializer<T>): List<T> =
        (get(key) as? JsonArray).orEmpty().mapNotNull {
            try {
                json.decodeFromJsonElement(serializer, it)
            } catch (e: SerializationException) {
                null
            } catch (e: IllegalArgumentException) {
                null
            }
        }

    fun encodeAck(seq: Long, state: AckState): String = buildJsonObject {
        put("seq", seq)
        put("state", state.wire)
    }.toString()

    fun parseAck(body: String): Boolean = json.decodeFromString(AckReply.serializer(), body).accepted

    fun encodeCommand(caller: Caller, data: String): String = buildJsonObject {
        when (caller) {
            is Caller.Person -> put("person_id", caller.id)
            is Caller.Chat -> put("chat_id", caller.id)
        }
        put("data", data)
    }.toString()

    fun parseCommand(body: String): String = json.decodeFromString(CommandReply.serializer(), body).text

    /** Lee `tele.json`; null si no es un objeto con los cuatro campos válidos. */
    fun parseRelease(body: String): Release? {
        val root = try {
            json.parseToJsonElement(body) as? JsonObject
        } catch (e: SerializationException) {
            null
        } ?: return null
        val code = root.number("version_code")?.toIntOrNull()?.takeIf { it >= 0 } ?: return null
        val name = root.text("version_name") ?: return null
        val sha = root.text("sha256")?.lowercase()?.takeIf { SHA256.matches(it) } ?: return null
        val size = root.number("size")?.toLongOrNull()?.takeIf { it > 0 } ?: return null
        return Release(code, name, sha, size)
    }

    private val SHA256 = Regex("[0-9a-f]{64}")

    private fun JsonObject.text(key: String): String? =
        (get(key) as? JsonPrimitive)?.takeIf { it.isString }?.content

    private fun JsonObject.number(key: String): String? =
        (get(key) as? JsonPrimitive)?.takeIf { !it.isString && it !is JsonNull }?.content

    /** El campo `error` de una respuesta del CT, o null si no lo trae. */
    fun parseError(body: String): String? = try {
        ((json.parseToJsonElement(body) as? JsonObject)?.get("error") as? JsonPrimitive)?.contentOrNull
    } catch (e: SerializationException) {
        null
    }
}
