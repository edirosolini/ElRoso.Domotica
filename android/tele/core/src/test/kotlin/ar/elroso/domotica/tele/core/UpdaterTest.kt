package ar.elroso.domotica.tele.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.io.IOException
import java.security.MessageDigest

/** Origen de prueba: escribe los bytes indicados o falla. */
class FakeApkSource(var bytes: ByteArray) : ApkSource {
    val fetched = mutableListOf<String>()
    var fails = false
    var onFetch: () -> Unit = {}

    override fun fetch(url: String, target: File, limit: Long) {
        fetched += "$url $limit"
        onFetch()
        if (fails) throw IOException("sin red")
        target.writeBytes(bytes)
    }
}

/** Instalador de prueba: anota la versión y el tamaño del archivo recibido. */
class FakeInstaller : ApkInstaller {
    val installed = mutableListOf<String>()
    var fails = false

    override fun install(file: File, release: Release) {
        if (fails) throw IllegalStateException("sesión rota")
        installed += "${release.versionCode} ${file.readBytes().size}"
    }
}

class UpdaterTest {

    @get:Rule
    val folder = TemporaryFolder()

    private val bytes = "apk nueva".toByteArray()
    private val sha = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
    private val transport = FakeTransport()
    private val urls = TeleUrls("http://casa")
    private var now = 0L
    private val policy = UpdatePolicy(own = 5, now = { now })
    private val source = FakeApkSource(bytes)
    private val installer = FakeInstaller()
    private val logs = mutableListOf<String>()
    private var alarm: Long? = null
    private var reminder = false
    private var playing = false
    private var awake = true
    private val target by lazy { folder.root.resolve("update.apk") }
    private val updater by lazy {
        Updater(
            api = TeleApi(transport, urls),
            urls = urls,
            policy = policy,
            source = source,
            installer = installer,
            target = target,
            alarm = { alarm },
            reminder = { reminder },
            playing = { playing },
            awake = { awake },
            allowed = { true },
            log = { logs += it },
        )
    }

    private fun publish(code: Int = 6, sha256: String = sha, size: Int = bytes.size) =
        transport.reply(200, """{"version_code": $code, "version_name": "0.3.0", "sha256": "$sha256", "size": $size}""")

    @Test
    fun downloadsVerifiesAndInstallsANewerVersion() {
        publish()

        updater.check()

        assertEquals(listOf("http://casa/app/tele.apk ${bytes.size}"), source.fetched)
        assertEquals(listOf("6 ${bytes.size}"), installer.installed)
        assertFalse(target.exists())
    }

    @Test
    fun theSameVersionIsNotDownloaded() {
        publish(code = 5)

        updater.check()

        assertEquals(emptyList<String>(), source.fetched)
    }

    @Test
    fun anUnpublishedOrUnreachableReleaseDoesNothing() {
        transport.reply(404, "")
        transport.fail()

        updater.check()
        updater.check()

        assertEquals(emptyList<String>(), source.fetched)
    }

    @Test
    fun notWithAnAlarmOrAPlay() {
        publish()
        publish()
        alarm = 7

        updater.check()
        alarm = null
        playing = true
        updater.check()

        assertEquals(emptyList<String>(), source.fetched)
    }

    @Test
    fun notWithAReminderOnScreen() {
        publish()
        reminder = true

        updater.check()

        assertEquals(emptyList<String>(), source.fetched)
        assertEquals("actualización: la 0.3.0 espera, hay un recordatorio en pantalla", logs.last())
    }

    @Test
    fun aReminderThatAppearsDuringTheDownloadStopsTheInstall() {
        publish()
        source.onFetch = { reminder = true }

        updater.check()

        assertEquals(emptyList<String>(), installer.installed)
    }

    @Test
    fun anAlarmThatStartsDuringTheDownloadStopsTheInstall() {
        publish()
        source.onFetch = { alarm = 7 }

        updater.check()

        assertEquals(emptyList<String>(), installer.installed)
        assertFalse(target.exists())
    }

    @Test
    fun aFileThatDoesNotMatchIsNotInstalledAndIsLogged() {
        publish(sha256 = "00".repeat(32))

        updater.check()

        assertEquals(emptyList<String>(), installer.installed)
        assertFalse(target.exists())
        assertEquals(true, logs.any { "sha256" in it })
    }

    @Test
    fun aFailedDownloadIsNotInstalled() {
        publish()
        source.fails = true

        updater.check()

        assertEquals(emptyList<String>(), installer.installed)
        assertFalse(target.exists())
    }

    @Test
    fun anOfferedVersionWaitsSixHours() {
        publish()
        publish()
        publish()

        updater.check()
        now = UpdatePolicy.RETRY_MS - 1
        updater.check()
        now = UpdatePolicy.RETRY_MS
        updater.check()

        assertEquals(2, installer.installed.size)
    }

    @Test
    fun anInstallThatFailsIsNotCountedAsOffered() {
        publish()
        publish()
        installer.fails = true

        updater.check()
        installer.fails = false
        updater.check()

        assertEquals(1, installer.installed.size)
        assertFalse(target.exists())
    }

    @Test
    fun notWithTheTeleAsleepButYesWhenItWakes() {
        publish()
        publish()
        awake = false

        updater.check()
        awake = true
        updater.check()

        assertEquals(1, source.fetched.size)
        assertEquals(1, installer.installed.size)
        assertEquals(true, logs.any { "reposo" in it })
    }
}
