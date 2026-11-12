package ar.elroso.domotica.tele.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class AlarmKeyTest {

    private val key = AlarmKey()

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

    @Test
    fun theSilencedSignStaysTwoSeconds() {
        assertEquals(2_000L, AlarmKey.SILENCED_MS)
    }

    @Test
    fun aPressSendsTheCommand() {
        key.alarm(7)

        assertEquals("callar 7", key.press(Caller.Person(3)))
    }

    @Test
    fun aSecondOkWhileWaitingIsIgnored() {
        key.alarm(7)
        key.press(Caller.Person(3))

        assertNull(key.press(Caller.Person(3)))
    }

    @Test
    fun aSecondOkOnTheSilencedAlarmIsIgnoredUntilThePollDropsIt() {
        key.alarm(7)
        key.press(Caller.Person(3))
        key.answered(7, replied = true)

        assertNull(key.press(Caller.Person(3)))
        key.alarm(7)
        assertNull(key.press(Caller.Person(3)))
        key.alarm(null)
        key.alarm(7)
        assertEquals("callar 7", key.press(Caller.Person(3)))
    }

    @Test
    fun anotherAlarmCanBeSilenced() {
        key.alarm(7)
        key.press(Caller.Person(3))
        key.answered(7, replied = true)

        key.alarm(8)

        assertEquals("callar 8", key.press(Caller.Person(3)))
    }

    @Test
    fun afterAFailureOkCanBeRetried() {
        key.alarm(7)
        key.press(Caller.Person(3))
        key.answered(7, replied = false)

        assertEquals("callar 7", key.press(Caller.Person(3)))
    }

    @Test
    fun withoutAlarmOrPersonAPressSendsNothing() {
        assertNull(key.press(Caller.Person(3)))
        key.alarm(7)
        assertNull(key.press(null))
    }

    @Test
    fun theSilencedAlarmIsKnown() {
        key.alarm(7)
        key.press(Caller.Person(3))
        key.answered(7, replied = true)

        assertEquals(true, key.silenced)
        key.alarm(null)
        assertEquals(false, key.silenced)
    }
}
