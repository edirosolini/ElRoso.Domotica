package ar.elroso.domotica.tele

import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import android.os.Build
import ar.elroso.domotica.tele.core.ApkInstaller
import ar.elroso.domotica.tele.core.Release
import java.io.File

/** Instala el APK con una sesión de `PackageInstaller`; el resultado llega a `InstallReceiver`. */
class SessionInstaller(private val context: Context) : ApkInstaller {

    override fun install(file: File, release: Release) {
        val installer = context.packageManager.packageInstaller
        abandonOpen(installer)
        val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL).apply {
            setAppPackageName(context.packageName)
            setSize(file.length())
        }
        val id = installer.createSession(params)
        installer.openSession(id).use { session ->
            try {
                session.openWrite("tele.apk", 0, file.length()).use { output ->
                    file.inputStream().use { it.copyTo(output) }
                    session.fsync(output)
                }
                session.commit(statusReceiver(id, release.versionCode).intentSender)
            } catch (e: Exception) {
                session.abandon()
                throw e
            }
        }
    }

    /** Abandona las sesiones propias que quedaron abiertas, para no apilar pantallas de confirmar. */
    private fun abandonOpen(installer: PackageInstaller) {
        installer.mySessions.forEach {
            try {
                installer.abandonSession(it.sessionId)
                Tele.log("actualización: abandono la sesión ${it.sessionId} que quedó abierta")
            } catch (e: Exception) {
                Tele.log("no pude abandonar la sesión ${it.sessionId}: ${e.javaClass.simpleName}: ${e.message}")
            }
        }
    }

    // El sistema completa los extras del estado: en Android 12 o más tiene que ser mutable.
    private fun statusReceiver(id: Int, versionCode: Int): PendingIntent {
        val mutable = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) PendingIntent.FLAG_MUTABLE else 0
        val intent = Intent(context, InstallReceiver::class.java).putExtra(InstallReceiver.EXTRA_VERSION_CODE, versionCode)
        return PendingIntent.getBroadcast(context, id, intent, PendingIntent.FLAG_UPDATE_CURRENT or mutable)
    }
}
