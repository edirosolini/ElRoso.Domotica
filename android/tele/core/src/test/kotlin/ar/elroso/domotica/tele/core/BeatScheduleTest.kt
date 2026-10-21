package ar.elroso.domotica.tele.core

import org.junit.Assert.assertEquals
import org.junit.Test

class BeatScheduleTest {

    @Test
    fun beatsEveryFiveSecondsWhileItWorks() {
        val schedule = BeatSchedule()

        assertEquals(5_000L, schedule.delay)
        assertEquals(5_000L, schedule.succeeded())
        assertEquals(5_000L, schedule.succeeded())
    }

    @Test
    fun backsOffUpToAMinuteWithoutNetwork() {
        val schedule = BeatSchedule()

        val delays = List(6) { schedule.failed() }

        assertEquals(listOf(10_000L, 20_000L, 40_000L, 60_000L, 60_000L, 60_000L), delays)
    }

    @Test
    fun goesBackToFiveSecondsWhenTheNetworkReturns() {
        val schedule = BeatSchedule()
        repeat(4) { schedule.failed() }

        assertEquals(5_000L, schedule.succeeded())
        assertEquals(10_000L, schedule.failed())
    }
}
