package ar.elroso.domotica.tele.core

import org.junit.Assert.assertEquals
import org.junit.Test

/** Reloj falso: dormir avanza el tiempo. */
class FakeTime {
    var now = 0L

    fun sleep(ms: Long) {
        now += ms
    }
}

/** El equipo de prueba: anota lo que se le pidió, con el reloj falso. */
class FakeDevice(private val time: FakeTime) : TeleDevice {
    val calls = mutableListOf<String>()
    // Cuánto tarda en prender después de despertarlo; null si no prende nunca.
    var wakesAfterMs: Long? = 0
    var playWorks = true
    var onPlay: () -> Unit = {}
    var level = 2
    override val volume get() = level
    override val maxVolume = 25
    private var wokeAt: Long? = null

    override val interactive: Boolean
        get() {
            val delay = wakesAfterMs ?: return false
            val since = wokeAt ?: return delay == 0L
            return time.now - since >= delay
        }

    override fun wake() {
        calls += "wake@${time.now}"
        if (wokeAt == null) wokeAt = time.now
    }

    override fun setVolume(index: Int) {
        calls += "volume $index"
        level = index
    }

    override fun play(url: String, seconds: Double?): Boolean {
        calls += "play $url@${time.now}"
        onPlay()
        return playWorks
    }

    override fun stopAudio() {
        calls += "stopAudio"
    }

    override fun show(url: String) {
        calls += "show $url"
    }

    override fun kiosk() {
        calls += "kiosk"
    }

    override fun hide() {
        calls += "hide"
    }
}

class OrderRunnerTest {

    private val time = FakeTime()
    private val device = FakeDevice(time)
    private val acks = mutableListOf<String>()
    private var onSleep: () -> Unit = {}
    private val runner = OrderRunner(
        device = device,
        ack = { seq, state -> acks += "$seq ${state.wire}" },
        log = {},
        sleep = {
            time.sleep(it)
            onSleep()
        },
        now = { time.now },
    )

    private val play = Order(5, OrderKind.PLAY, "http://casa/a.wav", 90, 2.0)
    private val stop = Order(9, OrderKind.STOP)

    @Test
    fun playWakesWaitsRaisesTheVolumePlaysAndRestoresIt() {
        device.wakesAfterMs = 1_000

        runner.run(play)

        assertEquals(listOf("5 received", "5 done"), acks)
        assertEquals(
            listOf("wake@0", "volume 23", "play http://casa/a.wav@21000", "volume 2"),
            device.calls,
        )
    }

    @Test
    fun theReceivedAckGoesBeforeAnything() {
        device.onPlay = { assertEquals(listOf("5 received"), acks) }

        runner.run(play)
    }

    @Test
    fun aVolumeAboveTheFloorIsNotTouched() {
        device.level = 24
        device.wakesAfterMs = 1_000

        runner.run(play)

        assertEquals(listOf("wake@0", "play http://casa/a.wav@21000"), device.calls)
    }

    @Test
    fun aTeleAlreadyOnPlaysWithoutTheSettleWait() {
        device.level = 24

        runner.run(play)

        assertEquals(listOf("wake@0", "play http://casa/a.wav@0"), device.calls)
    }

    @Test
    fun aTeleThatDoesNotWakeStillPlaysAfterTheCap() {
        device.wakesAfterMs = null

        runner.run(play)

        assertEquals("play http://casa/a.wav@30000", device.calls[2])
        assertEquals(listOf("5 received", "5 done"), acks)
    }

    @Test
    fun aPlayThatFailsIsAckedFailedAndRestoresTheVolume() {
        device.playWorks = false

        runner.run(play)

        assertEquals(listOf("5 received", "5 failed"), acks)
        assertEquals("volume 2", device.calls.last())
    }

    @Test
    fun aPlayWithoutUrlFails() {
        runner.run(Order(6, OrderKind.PLAY))

        assertEquals(listOf("6 received", "6 failed"), acks)
        assertEquals(emptyList<String>(), device.calls)
    }

    @Test
    fun aStopWhileWaitingCancelsThePlay() {
        device.wakesAfterMs = null
        onSleep = { if (time.now == 1_000L) runner.run(stop) }

        runner.run(play)

        assertEquals(listOf("5 received", "9 received"), acks)
        assertEquals(listOf("wake@0", "stopAudio", "kiosk"), device.calls)
    }

    @Test
    fun aStopWhilePlayingIsNotAFailure() {
        device.playWorks = false
        device.onPlay = { runner.run(stop) }

        runner.run(play)

        assertEquals(listOf("5 received", "9 received"), acks)
        assertEquals("volume 2", device.calls.last())
    }

    @Test
    fun showWakesAndPutsThePageInFront() {
        runner.run(Order(7, OrderKind.SHOW, "http://casa/alarma?job=3"))

        assertEquals(listOf("7 received"), acks)
        assertEquals(listOf("wake@0", "show http://casa/alarma?job=3"), device.calls)
    }

    @Test
    fun aShowWithoutUrlFails() {
        runner.run(Order(7, OrderKind.SHOW))

        assertEquals(listOf("7 received", "7 failed"), acks)
        assertEquals(emptyList<String>(), device.calls)
    }

    @Test
    fun stopCutsTheAudioAndGoesBackToTheKiosk() {
        runner.run(stop)

        assertEquals(listOf("9 received"), acks)
        assertEquals(listOf("stopAudio", "kiosk"), device.calls)
    }

    @Test
    fun hideLeavesTheScreen() {
        runner.run(Order(10, OrderKind.HIDE))

        assertEquals(listOf("10 received"), acks)
        assertEquals(listOf("hide"), device.calls)
    }

    @Test
    fun aRepeatedPlayThatEndedResendsReceivedAndDone() {
        runner.run(play)
        acks.clear()

        runner.resend(play)

        assertEquals(listOf("5 received", "5 done"), acks)
    }

    @Test
    fun aRepeatedPlayThatFailedResendsReceivedAndFailed() {
        device.playWorks = false
        runner.run(play)
        acks.clear()

        runner.resend(play)

        assertEquals(listOf("5 received", "5 failed"), acks)
    }

    @Test
    fun aRepeatedPlayStillSoundingResendsOnlyReceived() {
        device.onPlay = {
            acks.clear()
            runner.resend(play)
            assertEquals(listOf("5 received"), acks)
        }

        runner.run(play)
    }

    @Test
    fun aRepeatedShowResendsReceivedWithoutShowingAgain() {
        runner.run(Order(7, OrderKind.SHOW, "u"))
        acks.clear()
        device.calls.clear()

        runner.resend(Order(7, OrderKind.SHOW, "u"))

        assertEquals(listOf("7 received"), acks)
        assertEquals(emptyList<String>(), device.calls)
    }
}
