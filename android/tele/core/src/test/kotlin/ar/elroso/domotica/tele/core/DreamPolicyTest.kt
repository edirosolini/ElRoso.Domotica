package ar.elroso.domotica.tele.core

import org.junit.Assert.assertEquals
import org.junit.Test

class DreamPolicyTest {

    @Test
    fun withNothingTheKioskStays() {
        assertEquals(DreamDecision.KEEP, DreamPolicy.decide(alarm = null, reminder = false, quiet = false))
    }

    @Test
    fun anAlarmStopsIt() {
        assertEquals(DreamDecision.ALARM, DreamPolicy.decide(alarm = 7, reminder = false, quiet = false))
    }

    @Test
    fun aReminderStopsIt() {
        assertEquals(DreamDecision.REMINDER, DreamPolicy.decide(alarm = null, reminder = true, quiet = false))
    }

    @Test
    fun aQuietHouseStopsIt() {
        assertEquals(DreamDecision.QUIET, DreamPolicy.decide(alarm = null, reminder = false, quiet = true))
    }
}
