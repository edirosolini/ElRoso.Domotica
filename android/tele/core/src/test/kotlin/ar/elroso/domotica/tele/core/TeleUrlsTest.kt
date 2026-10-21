package ar.elroso.domotica.tele.core

import org.junit.Assert.assertEquals
import org.junit.Test

class TeleUrlsTest {

    private val urls = TeleUrls("http://casa.lan:8099")

    @Test
    fun buildsTheApiRoutes() {
        assertEquals("http://casa.lan:8099/api/tele/setup", urls.setup)
        assertEquals("http://casa.lan:8099/api/tele/hello", urls.hello)
        assertEquals("http://casa.lan:8099/api/tele/comedor/poll", urls.poll("comedor"))
        assertEquals("http://casa.lan:8099/api/tele/comedor/ack", urls.ack("comedor"))
        assertEquals("http://casa.lan:8099/api/command", urls.command)
    }

    @Test
    fun buildsTheKiosk() {
        assertEquals("http://casa.lan:8099/pantalla?ver=1", urls.kiosk)
    }

    @Test
    fun buildsTheAlarmView() {
        assertEquals("http://casa.lan:8099/alarma?job=7", urls.alarm(7))
    }

    @Test
    fun ignoresATrailingSlashInTheBase() {
        assertEquals("http://casa.lan:8099/api/tele/setup", TeleUrls("http://casa.lan:8099/").setup)
    }

    @Test
    fun encodesTheAliasAsAPathSegment() {
        assertEquals("http://casa.lan:8099/api/tele/sala%20grande%2F2/poll", urls.poll("sala grande/2"))
    }

    @Test
    fun buildsTheReleaseRoutes() {
        assertEquals("http://casa.lan:8099/app/tele.json", urls.release)
        assertEquals("http://casa.lan:8099/app/tele.apk", urls.apk)
    }
}
