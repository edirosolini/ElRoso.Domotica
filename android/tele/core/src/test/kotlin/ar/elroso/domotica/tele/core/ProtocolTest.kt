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
    fun readsTheErrorMessage() {
        assertEquals("Esa tele no tiene pantalla en la casa.", Protocol.parseError("""{"error": "Esa tele no tiene pantalla en la casa."}"""))
    }

    @Test
    fun errorOfABodyThatIsNotJsonIsNull() {
        assertNull(Protocol.parseError("<html>"))
    }
}
