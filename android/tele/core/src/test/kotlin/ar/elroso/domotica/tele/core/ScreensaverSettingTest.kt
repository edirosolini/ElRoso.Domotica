package ar.elroso.domotica.tele.core

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ScreensaverSettingTest {

    private val setting = ScreensaverSetting("ar.elroso.domotica.tele", "ar.elroso.domotica.tele.KioskDream")

    @Test
    fun nothingSetIsNotOurs() {
        assertFalse(setting.isOurs(null))
        assertFalse(setting.isOurs(""))
        assertFalse(setting.isOurs("  "))
    }

    @Test
    fun googlesBackdropIsNotOurs() {
        assertFalse(setting.isOurs("com.google.android.apps.tv.dreamx/.service.Backdrop"))
    }

    @Test
    fun theShortAndTheLongFormAreOurs() {
        assertTrue(setting.isOurs("ar.elroso.domotica.tele/.KioskDream"))
        assertTrue(setting.isOurs("ar.elroso.domotica.tele/ar.elroso.domotica.tele.KioskDream"))
    }

    @Test
    fun oursInsideAListIsOurs() {
        assertTrue(setting.isOurs("com.google.android.apps.tv.dreamx/.service.Backdrop, ar.elroso.domotica.tele/.KioskDream"))
        assertTrue(setting.isOurs("ar.elroso.domotica.tele/.KioskDream,com.google.android.apps.tv.dreamx/.service.Backdrop"))
    }

    @Test
    fun anotherClassOrPackageIsNotOurs() {
        assertFalse(setting.isOurs("ar.elroso.domotica.tele/.Otro"))
        assertFalse(setting.isOurs("ar.elroso.domotica.tele.otro/.KioskDream"))
        assertFalse(setting.isOurs("ar.elroso.domotica.tele"))
    }
}
