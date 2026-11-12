package ar.elroso.domotica.tele.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class TroubleTest {

    @Test
    fun withoutNetworkTheHouseIsNotFound() {
        assertEquals("No encuentro la casa. Revisá que la tele tenga WiFi.", Trouble.NO_HOUSE.text)
    }

    @Test
    fun anErrorOfTheHouseAsksToTryLater() {
        assertEquals("La casa no pudo hacerlo. Probá de nuevo en un rato.", Trouble.HOUSE_FAILED.text)
    }

    @Test
    fun noTextSpeaksOfHttpTheCtOrExceptions() {
        Trouble.entries.forEach {
            assertFalse(it.text, it.text.contains("HTTP"))
            assertFalse(it.text, it.text.contains("CT"))
            assertFalse(it.text, it.text.contains("Exception"))
        }
    }
}
