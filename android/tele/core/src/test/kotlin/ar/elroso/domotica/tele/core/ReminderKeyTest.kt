package ar.elroso.domotica.tele.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ReminderKeyTest {

    private val reminder = Reminder(9, "Regar", null, 0)

    @Test
    fun okMarksTheReminderDone() {
        assertEquals("hecho 9", ReminderKey.doneCommand(reminder, Caller.Person(3)))
        assertEquals("hecho 9", ReminderKey.doneCommand(reminder, Caller.Chat(-22)))
    }

    @Test
    fun okWithoutAPersonDoesNothing() {
        assertNull(ReminderKey.doneCommand(reminder, null))
    }

    @Test
    fun withAPersonOkIsDone() {
        assertEquals(ReminderKey.Action.DONE, ReminderKey.action(Remote.OK, Caller.Person(3)))
    }

    @Test
    fun withAPersonBackHidesItUntilTheNextNag() {
        assertEquals(ReminderKey.Action.LATER, ReminderKey.action(Remote.BACK, Caller.Chat(-22)))
    }

    @Test
    fun withoutAPersonOkAndBackClose() {
        assertEquals(ReminderKey.Action.CLOSE, ReminderKey.action(Remote.OK, null))
        assertEquals(ReminderKey.Action.CLOSE, ReminderKey.action(Remote.BACK, null))
    }

    @Test
    fun anyOtherKeyDoesNothing() {
        assertEquals(ReminderKey.Action.NONE, ReminderKey.action(Remote.OTHER, Caller.Person(3)))
        assertEquals(ReminderKey.Action.NONE, ReminderKey.action(Remote.OTHER, null))
    }
}
