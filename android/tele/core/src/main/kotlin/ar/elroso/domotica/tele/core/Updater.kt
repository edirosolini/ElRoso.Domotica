package ar.elroso.domotica.tele.core

import java.io.File
import java.io.IOException

/** De dónde se baja el APK; lanza IOException si no se pudo o si pasa de `limit` bytes. */
interface ApkSource {
    @Throws(IOException::class)
    fun fetch(url: String, target: File, limit: Long)
}

/** Abre la instalación del APK; lanza si no se pudo. */
interface ApkInstaller {
    fun install(file: File, release: Release)
}

/** Busca una versión nueva en el CT y, si corresponde, la baja, la verifica y abre su instalación. */
class Updater(
    private val api: TeleApi,
    private val urls: TeleUrls,
    private val policy: UpdatePolicy,
    private val source: ApkSource,
    private val installer: ApkInstaller,
    private val target: File,
    private val alarm: () -> Long?,
    private val reminder: () -> Boolean,
    private val playing: () -> Boolean,
    private val awake: () -> Boolean,
    private val dreaming: () -> Boolean,
    private val allowed: () -> Boolean,
    private val log: (String) -> Unit,
) {

    fun check() {
        val release = when (val result = api.release()) {
            is ReleaseResult.Published -> result.release
            ReleaseResult.Unpublished -> return log("actualización: no hay versión publicada")
            is ReleaseResult.Failed -> return log("actualización: no pude consultar tele.json (${result.reason})")
        }
        if (!ready(release)) return
        try {
            fetch(release)
        } finally {
            target.delete()
        }
    }

    private fun fetch(release: Release) {
        target.delete()
        try {
            source.fetch(urls.apk, target, release.size)
        } catch (e: IOException) {
            return log("actualización: no pude bajar la ${release.versionName} (${e.message})")
        }
        ApkCheck.verify(target, release)?.let {
            return log("actualización: descarto la ${release.versionName}, $it")
        }
        if (!ready(release)) return
        try {
            installer.install(target, release)
        } catch (e: Exception) {
            return log("actualización: no pude abrir la instalación (${e.javaClass.simpleName}: ${e.message})")
        }
        policy.offered(release)
        log("actualización: ofrezco instalar la ${release.versionName} (${release.versionCode})")
    }

    /** Si la política deja ofrecer esa versión ahora; si no, loguea por qué. */
    private fun ready(release: Release): Boolean {
        val decision = policy.decide(release, alarm(), playing(), awake(), allowed(), reminder(), dreaming())
        val why = when (decision) {
            UpdateDecision.OFFER -> return true
            UpdateDecision.CURRENT -> return false
            UpdateDecision.REJECTED -> "falló al instalarse y no se vuelve a ofrecer"
            UpdateDecision.RECENT -> "ya se ofreció hace menos de seis horas"
            UpdateDecision.ALARM -> "hay una alarma sonando"
            UpdateDecision.REMINDER -> "hay un recordatorio en pantalla"
            UpdateDecision.PLAYING -> "hay un audio en curso"
            UpdateDecision.ASLEEP -> "la tele está en reposo"
            UpdateDecision.DREAMING -> "el protector de pantalla está activo"
            UpdateDecision.NOT_ALLOWED -> "falta el permiso de instalar apps"
        }
        log("actualización: la ${release.versionName} espera, $why")
        return false
    }
}
