package ar.elroso.domotica.tele.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ProtocolTest {

    @Test
    fun parsesSetupIgnoringUnknownFields() {
        val body = """
            {"devices": ["comedor", "recamara"],
             "people": [{"chat_id": 11, "name": "Ana", "extra": true}, {"chat_id": -22, "name": "Beto"}],
             "nuevo": {"x": 1}}
        """

        val setup = Protocol.parseSetup(body)

        assertEquals(listOf("comedor", "recamara"), setup.devices)
        assertEquals(listOf(Person(11, "Ana"), Person(-22, "Beto")), setup.people)
    }

    @Test
    fun parsesSetupWithMissingListsAsEmpty() {
        val setup = Protocol.parseSetup("{}")

        assertEquals(emptyList<String>(), setup.devices)
        assertEquals(emptyList<Person>(), setup.people)
    }

    @Test
    fun encodesHelloWithTheContractNames() {
        val body = Protocol.encodeHello(Hello("comedor", "0.1.0", 3, listOf("overlay")))

        assertEquals(
            """{"alias":"comedor","version_name":"0.1.0","version_code":3,"caps":["overlay"]}""",
            body,
        )
    }

    @Test
    fun parsesHelloReplyIgnoringUnknownFields() {
        val reply = Protocol.parseHelloReply("""{"alias": "comedor", "caps": ["overlay"], "otro": 1}""")

        assertEquals(HelloReply("comedor", listOf("overlay")), reply)
    }

    @Test
    fun parsesPollWithAlarm() {
        assertEquals(PollReply(42), Protocol.parsePoll("""{"alarm": 42, "otro": "x"}"""))
    }

    @Test
    fun parsesPollWithoutAlarm() {
        assertNull(Protocol.parsePoll("""{"alarm": null}""").alarm)
    }

    @Test
    fun parsesPollOrders() {
        val reply = Protocol.parsePoll(
            """{"alarm": 7, "orders": [
                {"seq": 11, "kind": "play", "url": "http://casa/a.wav", "min_volume": 90, "seconds": 2.5},
                {"seq": 12, "kind": "show", "url": "http://casa/alarma?job=7"},
                {"seq": 13, "kind": "stop"},
                {"seq": 14, "kind": "hide", "extra": 1},
                {"seq": 15, "kind": "play", "url": "http://casa/b.wav", "min_volume": null, "seconds": null}]}""",
        )

        assertEquals(
            listOf(
                Order(11, OrderKind.PLAY, "http://casa/a.wav", 90, 2.5),
                Order(12, OrderKind.SHOW, "http://casa/alarma?job=7"),
                Order(13, OrderKind.STOP),
                Order(14, OrderKind.HIDE),
                Order(15, OrderKind.PLAY, "http://casa/b.wav"),
            ),
            reply.orders,
        )
    }

    @Test
    fun pollWithoutOrdersHasNone() {
        assertEquals(emptyList<Order>(), Protocol.parsePoll("""{"alarm": null}""").orders)
    }

    @Test
    fun pollSkipsUnknownKindsAndBrokenOrders() {
        val reply = Protocol.parsePoll(
            """{"alarm": null, "orders": [
                {"seq": 1, "kind": "dance"},
                {"seq": "x", "kind": "stop"},
                {"kind": "stop"},
                "stop",
                {"seq": 2, "kind": "stop"}]}""",
        )

        assertEquals(listOf(Order(2, OrderKind.STOP)), reply.orders)
    }

    @Test
    fun encodesTheAck() {
        assertEquals("""{"seq":11,"state":"received"}""", Protocol.encodeAck(11, AckState.RECEIVED))
        assertEquals("""{"seq":11,"state":"done"}""", Protocol.encodeAck(11, AckState.DONE))
        assertEquals("""{"seq":11,"state":"failed"}""", Protocol.encodeAck(11, AckState.FAILED))
    }

    @Test
    fun encodesTheCommand() {
        assertEquals("""{"chat_id":-22,"data":"callar 7"}""", Protocol.encodeCommand(-22, "callar 7"))
    }

    @Test
    fun readsTheErrorMessage() {
        assertEquals("Esa tele no tiene pantalla en la casa.", Protocol.parseError("""{"error": "Esa tele no tiene pantalla en la casa."}"""))
    }

    @Test
    fun errorOfABodyThatIsNotJsonIsNull() {
        assertNull(Protocol.parseError("<html>"))
    }

    @Test
    fun parsesTheReleaseIgnoringUnknownFields() {
        val body = """{"version_code": 6, "version_name": "0.3.0", "sha256": "ABABABABABABABABABABABABABABABABABABABABABABABABABABABABABABABAB", "size": 1234, "nuevo": 1}"""

        assertEquals(Release(6, "0.3.0", "abababababababababababababababababababababababababababababababab", 1234), Protocol.parseRelease(body))
    }

    @Test
    fun anInvalidReleaseIsNull() {
        val good = """"version_name": "0.3.0", "sha256": "abababababababababababababababababababababababababababababababab", "size": 1234"""
        assertNull(Protocol.parseRelease("<html>"))
        assertNull(Protocol.parseRelease("[]"))
        assertNull(Protocol.parseRelease("{$good}"))
        assertNull(Protocol.parseRelease("""{"version_code": "6", $good}"""))
        assertNull(Protocol.parseRelease("""{"version_code": true, $good}"""))
        assertNull(Protocol.parseRelease("""{"version_code": -1, $good}"""))
        assertNull(Protocol.parseRelease("""{"version_code": 6, "version_name": 3, "sha256": "abababababababababababababababababababababababababababababababab", "size": 1234}"""))
        assertNull(Protocol.parseRelease("""{"version_code": 6, "version_name": "0.3.0", "sha256": "abc", "size": 1234}"""))
        assertNull(Protocol.parseRelease("""{"version_code": 6, "version_name": "0.3.0", "sha256": "zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz", "size": 1234}"""))
        assertNull(Protocol.parseRelease("""{"version_code": 6, "version_name": "0.3.0", "sha256": "abababababababababababababababababababababababababababababababab", "size": 0}"""))
        assertNull(Protocol.parseRelease("""{"version_code": 6, "version_name": "0.3.0", "sha256": "abababababababababababababababababababababababababababababababab"}"""))
    }
}
