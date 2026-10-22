package ar.elroso.domotica.tele.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ReminderBoardTest {

    private val board = ReminderBoard()
    private val older = Reminder(4, "Regar", null, 0)
    private val newer = Reminder(9, "Sacar la basura", "Enano", 0)

    @Test
    fun withoutRemindersThereIsNoCard() {
        assertNull(board.card)
        board.reminders(emptyList())
        assertNull(board.card)
    }

    @Test
    fun showsTheOldestOneAtATime() {
        board.reminders(listOf(newer, older))

        assertEquals(older, board.card)
    }

    @Test
    fun nothingWhileAnAlarmRings() {
        board.reminders(listOf(older))
        board.alarm(7)

        assertNull(board.card)

        board.alarm(null)
        assertEquals(older, board.card)
    }

    @Test
    fun theCardFollowsTheNagsOfTheReminder() {
        board.reminders(listOf(older))
        board.reminders(listOf(older.copy(nags = 1)))

        assertEquals(older.copy(nags = 1), board.card)
    }

    @Test
    fun aDismissedOneLetsTheNextThrough() {
        board.reminders(listOf(older, newer))

        board.dismiss(older)

        assertEquals(newer, board.card)
    }

    @Test
    fun aDismissedOneComesBackWhenItIsNaggedAgain() {
        board.reminders(listOf(older))
        board.dismiss(older)
        board.reminders(listOf(older))
        assertNull(board.card)

        board.reminders(listOf(older.copy(nags = 1)))

        assertEquals(older.copy(nags = 1), board.card)
    }

    @Test
    fun aDoneOneDoesNotComeBackWhileThePollStillBringsIt() {
        board.reminders(listOf(older, newer))

        board.done(older.id)
        assertEquals(newer, board.card)

        board.reminders(listOf(older.copy(nags = 1), newer))
        assertEquals(newer, board.card)
    }

    @Test
    fun aReminderThatLeavesThePollIsForgotten() {
        board.reminders(listOf(older))
        board.dismiss(older)
        board.reminders(emptyList())

        board.reminders(listOf(older))

        assertEquals(older, board.card)
    }

    @Test
    fun aDoneIdIsForgottenOnceThePollDropsIt() {
        board.reminders(listOf(older))
        board.done(older.id)
        board.reminders(emptyList())

        board.reminders(listOf(older))

        assertEquals(older, board.card)
    }
}
