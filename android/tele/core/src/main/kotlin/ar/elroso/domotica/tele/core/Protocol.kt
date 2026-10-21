package ar.elroso.domotica.tele.core

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.SerializationException
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

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

/** La respuesta de `poll`: la alarma que suena en la tele, o null. */
@Serializable
data class PollReply(val alarm: Long? = null)

/** Parseo y armado del JSON del contrato con el CT. */
object Protocol {
    private val json = Json { ignoreUnknownKeys = true }

    fun parseSetup(body: String): Setup = json.decodeFromString(Setup.serializer(), body)

    fun encodeHello(hello: Hello): String = json.encodeToString(Hello.serializer(), hello)

    fun parseHelloReply(body: String): HelloReply = json.decodeFromString(HelloReply.serializer(), body)

    fun parsePoll(body: String): PollReply = json.decodeFromString(PollReply.serializer(), body)

    /** El campo `error` de una respuesta del CT, o null si no lo trae. */
    fun parseError(body: String): String? = try {
        ((json.parseToJsonElement(body) as? JsonObject)?.get("error") as? JsonPrimitive)?.contentOrNull
    } catch (e: SerializationException) {
        null
    }
}
