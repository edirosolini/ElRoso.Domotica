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
}
