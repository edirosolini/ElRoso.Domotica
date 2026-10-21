package ar.elroso.domotica.tele.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
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

    @Test
    fun anOldChoiceWithAChatKeepsSilencingAsThatChat() {
        assertEquals(Caller.Chat(-22), TeleChoice(alias = "comedor", chatId = -22).caller)
    }

    @Test
    fun aPersonWinsOverAChat() {
        assertEquals(Caller.Person(3), TeleChoice(alias = "comedor", chatId = -22, personId = 3).caller)
    }

    @Test
    fun withoutPersonOrChatThereIsNoCaller() {
        assertNull(TeleChoice(alias = "comedor", chatId = null).caller)
    }

    @Test
    fun choosingAPersonForgetsTheOldChat() {
        val choice = TeleChoice.of("comedor", Caller.Person(3))

        assertEquals(TeleChoice(alias = "comedor", chatId = null, personId = 3), choice)
    }

    @Test
    fun choosingAChatHasNoPerson() {
        assertEquals(TeleChoice(alias = "comedor", chatId = -22, personId = null), TeleChoice.of("comedor", Caller.Chat(-22)))
        assertEquals(TeleChoice(alias = "comedor", chatId = null, personId = null), TeleChoice.of("comedor", null))
    }

    @Test
    fun withARosterTheOwnersAreItsPeopleWithOrWithoutChat() {
        val setup = Setup(
            devices = listOf("comedor"),
            people = listOf(Person(11, "Papá")),
            persons = listOf(Resident(3, "Enano", null), Resident(1, "Papá", 11)),
        )

        assertEquals(
            listOf(Owner("Enano (sin Telegram)", Caller.Person(3)), Owner("Papá", Caller.Person(1))),
            Owners.of(setup),
        )
    }

    @Test
    fun withoutARosterTheOwnersAreTheChats() {
        val setup = Setup(devices = listOf("comedor"), people = listOf(Person(11, "Ana"), Person(-22, "Beto")))

        assertEquals(
            listOf(Owner("Ana", Caller.Chat(11)), Owner("Beto", Caller.Chat(-22))),
            Owners.of(setup),
        )
    }

    @Test
    fun withNobodyThereAreNoOwners() {
        assertEquals(emptyList<Owner>(), Owners.of(Setup(devices = listOf("comedor"))))
    }
}
