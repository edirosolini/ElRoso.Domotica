package ar.elroso.domotica.tele

import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.media.MediaPlayer
import android.os.PowerManager
import ar.elroso.domotica.tele.core.TeleDevice
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/** El equipo de verdad: pantalla, volumen de música, reproducción y el kiosco. */
class AndroidDevice(private val context: Context) : TeleDevice {

    companion object {
        // Cuánto queda prendida la pantalla después de despertarla.
        private const val WAKE_HOLD_MS = 60_000L
        // Cuánto más que el clip se espera a que termine; sin duración, el tope.
        private const val PLAY_MARGIN_MS = 15_000L
        private const val PLAY_TIMEOUT_MS = 120_000L
    }

    /** Un audio en curso, para poder cortarlo desde otro hilo. */
    private class Playback(val player: MediaPlayer) {
        val finished = CountDownLatch(1)
        @Volatile var completed = false
        @Volatile var cancelled = false
    }

    private val power = context.getSystemService(PowerManager::class.java)
    private val audio = context.getSystemService(AudioManager::class.java)
    @Suppress("DEPRECATION")
    private val wakeLock = power.newWakeLock(
        PowerManager.SCREEN_BRIGHT_WAKE_LOCK or PowerManager.ACQUIRE_CAUSES_WAKEUP or PowerManager.ON_AFTER_RELEASE,
        "domotica:wake",
    ).apply { setReferenceCounted(false) }
    private val lock = Any()
    private var current: Playback? = null

    override val interactive: Boolean get() = power.isInteractive
    override val volume: Int get() = audio.getStreamVolume(AudioManager.STREAM_MUSIC)
    override val maxVolume: Int get() = audio.getStreamMaxVolume(AudioManager.STREAM_MUSIC)

    override fun wake() {
        wakeLock.acquire(WAKE_HOLD_MS)
    }

    override fun setVolume(index: Int) {
        audio.setStreamVolume(AudioManager.STREAM_MUSIC, index, 0)
    }

    override fun play(url: String, seconds: Double?): Boolean {
        val attributes = AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_MEDIA)
            .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
            .build()
        val focus = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT)
            .setAudioAttributes(attributes)
            .build()
        val playback = Playback(MediaPlayer())
        val player = playback.player
        synchronized(lock) { current = playback }
        audio.requestAudioFocus(focus)
        try {
            player.setAudioAttributes(attributes)
            player.setOnCompletionListener {
                playback.completed = true
                playback.finished.countDown()
            }
            player.setOnErrorListener { _, what, extra ->
                Tele.log("el reproductor falló: $what/$extra")
                playback.finished.countDown()
                true
            }
            player.setDataSource(url)
            player.prepare()
            synchronized(lock) {
                if (playback.cancelled) return false
                player.start()
            }
            val limit = seconds?.let { (it * 1000).toLong() + PLAY_MARGIN_MS } ?: PLAY_TIMEOUT_MS
            if (!playback.finished.await(limit, TimeUnit.MILLISECONDS)) Tele.log("el audio no terminó a tiempo")
            return playback.completed
        } catch (e: Exception) {
            Tele.log("no pude reproducir el audio: ${e.javaClass.simpleName}: ${e.message}")
            return false
        } finally {
            synchronized(lock) { if (current === playback) current = null }
            player.release()
            audio.abandonAudioFocusRequest(focus)
        }
    }

    override fun stopAudio() {
        synchronized(lock) {
            val playback = current ?: return
            playback.cancelled = true
            try {
                if (playback.player.isPlaying) playback.player.stop()
            } catch (e: IllegalStateException) {
                Tele.log("el reproductor no estaba listo para cortar")
            }
            playback.finished.countDown()
        }
    }

    override fun show(url: String) {
        val intent = Intent(context, MainActivity::class.java)
            .putExtra(MainActivity.EXTRA_URL, url)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_REORDER_TO_FRONT)
        context.startActivity(intent)
    }

    override fun kiosk() {
        Kiosk.load(Tele.urls.kiosk)
    }

    override fun hide() {
        Kiosk.leave()
    }
}
