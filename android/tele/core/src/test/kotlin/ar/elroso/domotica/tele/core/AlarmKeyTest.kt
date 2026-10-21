package ar.elroso.domotica.tele.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class AlarmKeyTest {

    @Test
    fun okWithAnAlarmSilencesIt() {
        assertEquals("callar 7", AlarmKey.offCommand(alarm = 7, chatId = -22))
    }

    @Test
    fun okWithoutAlarmDoesNothing() {
        assertNull(AlarmKey.offCommand(alarm = null, chatId = -22))
    }

    @Test
    fun okWithoutAPersonDoesNothing() {
        assertNull(AlarmKey.offCommand(alarm = 7, chatId = null))
    }
}
