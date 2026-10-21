package ar.elroso.domotica.tele.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class AlarmKeyTest {

    @Test
    fun okWithAnAlarmSilencesIt() {
        assertEquals("callar 7", AlarmKey.offCommand(alarm = 7, caller = Caller.Chat(-22)))
    }

    @Test
    fun okSilencesItAsAPersonOfTheRoster() {
        assertEquals("callar 7", AlarmKey.offCommand(alarm = 7, caller = Caller.Person(3)))
    }

    @Test
    fun okWithoutAlarmDoesNothing() {
        assertNull(AlarmKey.offCommand(alarm = null, caller = Caller.Chat(-22)))
    }

    @Test
    fun okWithoutAPersonDoesNothing() {
        assertNull(AlarmKey.offCommand(alarm = 7, caller = null))
    }
}
