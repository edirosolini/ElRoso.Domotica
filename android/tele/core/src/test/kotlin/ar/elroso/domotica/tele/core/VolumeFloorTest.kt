package ar.elroso.domotica.tele.core

import org.junit.Assert.assertEquals
import org.junit.Test

class VolumeFloorTest {

    @Test
    fun theFloorOfTheHouseIsRoundedUpToTheStep() {
        assertEquals(14, VolumeFloor.index(90, 15))
        assertEquals(23, VolumeFloor.index(90, 25))
        assertEquals(9, VolumeFloor.index(60, 15))
        assertEquals(15, VolumeFloor.index(60, 25))
    }

    @Test
    fun withoutFloorItIsHalf() {
        assertEquals(8, VolumeFloor.index(null, 15))
        assertEquals(13, VolumeFloor.index(null, 25))
    }

    @Test
    fun staysWithinTheStream() {
        assertEquals(15, VolumeFloor.index(150, 15))
        assertEquals(0, VolumeFloor.index(-5, 25))
        assertEquals(0, VolumeFloor.index(90, 0))
    }
}
