package ar.elroso.domotica.tele.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test
import java.io.IOException

/** Transporte de prueba: contesta lo encolado y anota cada pedido. */
class FakeTransport : Transport {
    val requests = mutableListOf<String>()
    val bodies = mutableListOf<String>()
    private val replies = ArrayDeque<() -> HttpReply>()

    fun reply(status: Int, body: String) = replies.addLast { HttpReply(status, body) }

    fun fail() = replies.addLast { throw IOException("sin red") }

    override fun get(url: String): HttpReply {
        requests += "GET $url"
        return replies.removeFirst()()
    }

    override fun postJson(url: String, body: String): HttpReply {
        requests += "POST $url"
        bodies += body
        return replies.removeFirst()()
    }
}

class TeleApiTest {

    private val transport = FakeTransport()
    private val api = TeleApi(transport, TeleUrls("http://casa"))

    @Test
    fun setupReadsTheDevicesAndPeople() {
        transport.reply(200, """{"devices": ["comedor"], "people": [{"chat_id": 1, "name": "Ana"}]}""")

        assertEquals(Setup(listOf("comedor"), listOf(Person(1, "Ana"))), api.setup())
        assertEquals(listOf("GET http://casa/api/tele/setup"), transport.requests)
    }

    @Test
    fun setupThatFailsSaysWhy() {
        transport.reply(404, """{"error": "no existe"}""")

        val error = assertThrows(TeleFailure::class.java) { api.setup() }

        assertEquals("HTTP 404: no existe", error.message)
    }

    @Test
    fun setupWithoutNetworkIsAFailure() {
        transport.fail()

        val error = assertThrows(TeleFailure::class.java) { api.setup() }

        assertEquals("sin red", error.message)
    }

    @Test
    fun helloPostsTheRegistration() {
        transport.reply(200, """{"alias": "comedor", "caps": []}""")

        val result = api.hello(Hello("comedor", "0.1.0", 1, emptyList()))

        assertEquals(HelloResult.Accepted(emptyList()), result)
        assertEquals(listOf("POST http://casa/api/tele/hello"), transport.requests)
    }

    @Test
    fun helloRejectedCarriesTheReason() {
        transport.reply(400, """{"error": "Esa tele no tiene pantalla en la casa."}""")

        val result = api.hello(Hello("living", "0.1.0", 1, emptyList()))

        assertEquals(HelloResult.Rejected(400, "Esa tele no tiene pantalla en la casa."), result)
    }

    @Test
    fun helloWithoutNetworkFails() {
        transport.fail()

        assertEquals(HelloResult.Failed("sin red"), api.hello(Hello("comedor", "0.1.0", 1, emptyList())))
    }

    @Test
    fun pollReadsTheAlarm() {
        transport.reply(200, """{"alarm": 7}""")

        assertEquals(PollResult.Alarm(7), api.poll("comedor"))
        assertEquals(listOf("GET http://casa/api/tele/comedor/poll"), transport.requests)
    }

    @Test
    fun pollOfAnUnregisteredTeleIsNotRegistered() {
        transport.reply(404, """{"error": "Esa tele no está registrada."}""")

        assertEquals(PollResult.NotRegistered, api.poll("comedor"))
    }

    @Test
    fun pollWithAServerErrorFails() {
        transport.reply(500, """{"error": "No pude atender a la tele."}""")

        assertEquals(PollResult.Failed("HTTP 500: No pude atender a la tele."), api.poll("comedor"))
    }

    @Test
    fun pollReadsTheOrders() {
        transport.reply(200, """{"alarm": null, "orders": [{"seq": 3, "kind": "stop"}]}""")

        assertEquals(PollResult.Alarm(null, listOf(Order(3, OrderKind.STOP))), api.poll("comedor"))
    }

    @Test
    fun ackPostsTheStateOfTheOrder() {
        transport.reply(200, """{"accepted": true}""")

        assertEquals(AckResult.Answered(true), api.ack("comedor", 3, AckState.DONE))
        assertEquals(listOf("POST http://casa/api/tele/comedor/ack"), transport.requests)
        assertEquals(listOf("""{"seq":3,"state":"done"}"""), transport.bodies)
    }

    @Test
    fun aLateAckIsAnsweredAsNotAccepted() {
        transport.reply(200, """{"accepted": false}""")

        assertEquals(AckResult.Answered(false), api.ack("comedor", 3, AckState.RECEIVED))
    }

    @Test
    fun ackWithoutNetworkOrRejectedFails() {
        transport.fail()
        transport.reply(404, """{"error": "Esa tele no está registrada."}""")

        assertEquals(AckResult.Failed("sin red"), api.ack("comedor", 3, AckState.DONE))
        assertEquals(AckResult.Failed("HTTP 404: Esa tele no está registrada."), api.ack("comedor", 3, AckState.DONE))
    }

    @Test
    fun commandPostsAsThePersonAndReadsTheReply() {
        transport.reply(200, """{"text": "Apagada", "actions": []}""")

        assertEquals(CommandResult.Replied("Apagada"), api.command(-22, "callar 7"))
        assertEquals(listOf("POST http://casa/api/command"), transport.requests)
        assertEquals(listOf("""{"chat_id":-22,"data":"callar 7"}"""), transport.bodies)
    }

    @Test
    fun commandThatFailsSaysWhy() {
        transport.reply(400, """{"error": "Ese chat no es de la casa."}""")
        transport.fail()

        assertEquals(CommandResult.Failed("HTTP 400: Ese chat no es de la casa."), api.command(1, "callar 7"))
        assertEquals(CommandResult.Failed("sin red"), api.command(1, "callar 7"))
    }
}
