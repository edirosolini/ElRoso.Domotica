package ar.elroso.domotica.tele.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class TeleChoiceTest {

    @Test
    fun withoutAliasItIsNotReady() {
        assertFalse(TeleChoice(alias = null, chatId = 11).ready)
        assertFalse(TeleChoice(alias = "  ", chatId = 11).ready)
    }

    @Test
    fun withAliasItIsReady() {
        assertTrue(TeleChoice(alias = "comedor", chatId = null).ready)
    }

    @Test
    fun capsAnnounceOnlyWhatTheAppDoes() {
        assertEquals(listOf("play"), Caps.of(overlay = false))
        assertEquals(listOf("play", "show", "overlay"), Caps.of(overlay = true))
    }
}
