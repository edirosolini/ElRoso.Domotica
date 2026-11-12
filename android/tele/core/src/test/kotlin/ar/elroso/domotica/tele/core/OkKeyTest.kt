package ar.elroso.domotica.tele.core

import org.junit.Assert.assertEquals
import org.junit.Test

class OkKeyTest {

    private val key = OkKey()

    @Test
    fun aShortOkWithoutAlarmDoesNothing() {
        assertEquals(OkKey.Action.NONE, key.down(1_000, repeat = false, alarm = false))
        assertEquals(OkKey.Action.NONE, key.up(1_300, alarm = false))
    }

    @Test
    fun holdingOkThreeSecondsWithoutAlarmOpensTheChange() {
        key.down(1_000, repeat = false, alarm = false)

        assertEquals(OkKey.Action.NONE, key.down(3_999, repeat = true, alarm = false))
        assertEquals(OkKey.Action.CHANGE, key.down(4_000, repeat = true, alarm = false))
    }

    @Test
    fun theChangeOpensOnlyOncePerPress() {
        key.down(1_000, repeat = false, alarm = false)
        key.down(4_000, repeat = true, alarm = false)

        assertEquals(OkKey.Action.NONE, key.down(4_050, repeat = true, alarm = false))
        assertEquals(OkKey.Action.NONE, key.up(4_100, alarm = false))
    }

    @Test
    fun withoutRepeatsReleasingAfterThreeSecondsOpensTheChange() {
        key.down(1_000, repeat = false, alarm = false)

        assertEquals(OkKey.Action.CHANGE, key.up(4_000, alarm = false))
    }

    @Test
    fun releasingBeforeThreeSecondsDoesNotOpenIt() {
        key.down(1_000, repeat = false, alarm = false)

        assertEquals(OkKey.Action.NONE, key.up(3_999, alarm = false))
    }

    @Test
    fun aNewPressStartsTheCountAgain() {
        key.down(1_000, repeat = false, alarm = false)
        key.up(1_200, alarm = false)
        key.down(5_000, repeat = false, alarm = false)

        assertEquals(OkKey.Action.NONE, key.down(6_000, repeat = true, alarm = false))
        assertEquals(OkKey.Action.NONE, key.up(6_100, alarm = false))
    }

    @Test
    fun aReleaseWithoutItsPressDoesNotOpenIt() {
        assertEquals(OkKey.Action.NONE, key.up(9_000, alarm = false))
    }

    @Test
    fun withAnAlarmReleasingOkSilencesIt() {
        key.down(1_000, repeat = false, alarm = true)

        assertEquals(OkKey.Action.SILENCE, key.up(1_200, alarm = true))
    }

    @Test
    fun withAnAlarmHoldingOkNeverOpensTheChangeAndReleasingSilences() {
        key.down(1_000, repeat = false, alarm = true)

        assertEquals(OkKey.Action.NONE, key.down(5_000, repeat = true, alarm = true))
        assertEquals(OkKey.Action.SILENCE, key.up(6_000, alarm = true))
    }
}
