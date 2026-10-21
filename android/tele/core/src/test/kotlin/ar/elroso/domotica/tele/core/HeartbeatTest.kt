package ar.elroso.domotica.tele.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

class HeartbeatTest {

    private val transport = FakeTransport()
    private val logs = mutableListOf<String>()
    private var caps = emptyList<String>()

    private fun heartbeat(choice: TeleChoice = TeleChoice("comedor", 11)) = Heartbeat.forChoice(
        choice = choice,
        api = TeleApi(transport, TeleUrls("http://casa")),
        version = AppVersion("0.1.0", 3),
        caps = { caps },
        log = { logs += it },
    )

    private fun ready() = heartbeat()!!

    @Test
    fun withoutAliasThereIsNoHeartbeat() {
        assertNull(heartbeat(TeleChoice(null, 11)))
        assertNotNull(heartbeat(TeleChoice("comedor", null)))
    }

    @Test
    fun firstTickSaysHelloAndThenPolls() {
        val beat = ready()
        transport.reply(200, """{"alias": "comedor", "caps": []}""")
        transport.reply(200, """{"alarm": null}""")

        assertEquals(5_000L, beat.tick())
        assertEquals(5_000L, beat.tick())

        assertEquals(
            listOf("POST http://casa/api/tele/hello", "GET http://casa/api/tele/comedor/poll"),
            transport.requests,
        )
        assertEquals(
            listOf("""{"alias":"comedor","version_name":"0.1.0","version_code":3,"caps":[]}"""),
            transport.bodies,
        )
    }

    @Test
    fun logsTheAlarmOnlyWhenItChanges() {
        val beat = ready()
        transport.reply(200, """{"alias": "comedor", "caps": []}""")
        listOf("7", "7", "null").forEach { transport.reply(200, """{"alarm": $it}""") }

        repeat(4) { beat.tick() }

        assertEquals(1, logs.count { it == "alarma en la tele: 7" })
        assertEquals(1, logs.count { it == "la tele ya no tiene alarma" })
    }

    @Test
    fun anUnregisteredPollSaysHelloAgain() {
        val beat = ready()
        transport.reply(200, """{"alias": "comedor", "caps": []}""")
        transport.reply(404, """{"error": "Esa tele no está registrada."}""")
        transport.reply(200, """{"alias": "comedor", "caps": []}""")

        repeat(3) { beat.tick() }

        assertEquals("POST http://casa/api/tele/hello", transport.requests.last())
    }

    @Test
    fun backsOffWithoutNetworkAndRecovers() {
        val beat = ready()
        transport.fail()
        transport.fail()
        transport.reply(200, """{"alias": "comedor", "caps": []}""")

        assertEquals(10_000L, beat.tick())
        assertEquals(20_000L, beat.tick())
        assertEquals(5_000L, beat.tick())
    }

    @Test
    fun aRejectedHelloIsLoggedAndRetriedLater() {
        val beat = ready()
        transport.reply(400, """{"error": "Esa tele no tiene pantalla en la casa."}""")
        transport.reply(200, """{"alias": "comedor", "caps": []}""")

        assertEquals(10_000L, beat.tick())
        beat.tick()

        assertEquals("el CT rechazó el registro (400): Esa tele no tiene pantalla en la casa.", logs.first())
        assertEquals(2, transport.requests.count { it.startsWith("POST") })
    }

    @Test
    fun newCapsSayHelloAgain() {
        val beat = ready()
        transport.reply(200, """{"alias": "comedor", "caps": []}""")
        transport.reply(200, """{"alias": "comedor", "caps": ["overlay"]}""")

        beat.tick()
        caps = listOf("overlay")
        beat.tick()

        assertEquals(
            """{"alias":"comedor","version_name":"0.1.0","version_code":3,"caps":["overlay"]}""",
            transport.bodies.last(),
        )
    }
}
