package ar.elroso.domotica.tele.core

import org.junit.Assert.assertEquals
import org.junit.Test

class UpdatePolicyTest {

    private var now = 0L
    private val offers = MemoryOfferLog()
    private val policy = UpdatePolicy(own = 5, offers = offers, now = { now })
    private val next = Release(6, "0.3.0", "ab".repeat(32), 10)

    private fun decide(
        release: Release = next,
        alarm: Long? = null,
        playing: Boolean = false,
        awake: Boolean = true,
        allowed: Boolean = true,
        reminder: Boolean = false,
    ) = policy.decide(release, alarm, playing, awake, allowed, reminder)

    @Test
    fun offersANewerVersion() {
        assertEquals(UpdateDecision.OFFER, decide())
    }

    @Test
    fun theSameOrAnOlderVersionIsCurrent() {
        assertEquals(UpdateDecision.CURRENT, decide(next.copy(versionCode = 5)))
        assertEquals(UpdateDecision.CURRENT, decide(next.copy(versionCode = 4)))
    }

    @Test
    fun notWithAnAlarmOrAPlayInCourse() {
        assertEquals(UpdateDecision.ALARM, decide(alarm = 7))
        assertEquals(UpdateDecision.PLAYING, decide(playing = true))
    }

    @Test
    fun notWithoutPermissionToInstall() {
        assertEquals(UpdateDecision.NOT_ALLOWED, decide(allowed = false))
    }

    @Test
    fun theSameVersionIsNotOfferedAgainForSixHours() {
        now = 1_000
        policy.offered(next)

        now = 1_000 + UpdatePolicy.RETRY_MS - 1
        assertEquals(UpdateDecision.RECENT, decide())
        now = 1_000 + UpdatePolicy.RETRY_MS
        assertEquals(UpdateDecision.OFFER, decide())
    }

    @Test
    fun aNewerVersionIsOfferedRightAway() {
        policy.offered(next)

        assertEquals(UpdateDecision.OFFER, decide(next.copy(versionCode = 7)))
    }

    @Test
    fun theLastOfferSurvivesInTheLog() {
        now = 1_000
        policy.offered(next)

        val again = UpdatePolicy(own = 5, offers = offers, now = { now })

        assertEquals(UpdateDecision.RECENT, again.decide(next, null, false, true, true))
    }

    @Test
    fun anOfferInTheFutureDoesNotBlock() {
        now = 10_000
        policy.offered(next)
        now = 1_000

        assertEquals(UpdateDecision.OFFER, decide())
    }

    @Test
    fun notWithTheTeleAsleep() {
        assertEquals(UpdateDecision.ASLEEP, decide(awake = false))
    }

    @Test
    fun aRejectedVersionIsNeverOfferedAgain() {
        policy.rejected(6)

        now = 100 * UpdatePolicy.RETRY_MS
        assertEquals(UpdateDecision.REJECTED, decide())
        assertEquals(UpdateDecision.REJECTED, UpdatePolicy(own = 5, offers = offers, now = { now }).decide(next, null, false, true, true))
    }

    @Test
    fun aVersionAboveTheRejectedOneIsOffered() {
        policy.rejected(6)

        assertEquals(UpdateDecision.OFFER, decide(next.copy(versionCode = 7)))
    }

    @Test
    fun notWithAReminderOnScreen() {
        assertEquals(UpdateDecision.REMINDER, decide(reminder = true))
    }

    @Test
    fun theAlarmGoesBeforeTheReminderAndTheReminderBeforeTheAudio() {
        assertEquals(UpdateDecision.ALARM, decide(alarm = 7, reminder = true))
        assertEquals(UpdateDecision.REMINDER, decide(reminder = true, playing = true))
    }
}
