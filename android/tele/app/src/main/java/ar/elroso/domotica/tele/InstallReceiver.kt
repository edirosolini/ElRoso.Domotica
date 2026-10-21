package ar.elroso.domotica.tele

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import android.os.Build
import ar.elroso.domotica.tele.core.UpdatePolicy

/** Recibe el estado de la instalación: abre la pantalla de confirmar o loguea cómo terminó. */
class InstallReceiver : BroadcastReceiver() {

    companion object {
        /** El `versionCode` que se está instalando. */
        const val EXTRA_VERSION_CODE = "version_code"

        // Fallas que no se arreglan reintentando la misma versión.
        private val DEFINITIVE = setOf(
            PackageInstaller.STATUS_FAILURE_INCOMPATIBLE,
            PackageInstaller.STATUS_FAILURE_CONFLICT,
            PackageInstaller.STATUS_FAILURE_INVALID,
        )
    }

    override fun onReceive(context: Context, intent: Intent) {
        val status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)
        when (status) {
            PackageInstaller.STATUS_PENDING_USER_ACTION -> confirm(context, intent)
            PackageInstaller.STATUS_SUCCESS -> Tele.log("actualización instalada")
            PackageInstaller.STATUS_FAILURE_ABORTED -> Tele.log("actualización cancelada en la tele")
            in DEFINITIVE -> reject(context, intent, status)
            else -> Tele.log(
                "la actualización falló ($status): ${intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE)}"
            )
        }
    }

    /** Anota la versión como rechazada para no volver a ofrecerla. */
    private fun reject(context: Context, intent: Intent, status: Int) {
        val message = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE)
        val code = intent.getIntExtra(EXTRA_VERSION_CODE, -1)
        if (code < 0) return Tele.log("la actualización falló sin arreglo ($status): $message")
        UpdatePolicy(Tele.version.code, Tele.offers(context)).rejected(code)
        Tele.log("la actualización $code falló sin arreglo ($status): $message; no se vuelve a ofrecer")
    }

    /** Abre la pantalla del sistema para aceptar la instalación con el control. */
    private fun confirm(context: Context, intent: Intent) {
        val screen = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            intent.getParcelableExtra(Intent.EXTRA_INTENT, Intent::class.java)
        } else {
            @Suppress("DEPRECATION")
            intent.getParcelableExtra(Intent.EXTRA_INTENT)
        }
        if (screen == null) return Tele.log("la instalación pide confirmar pero no trae la pantalla")
        try {
            context.startActivity(screen.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            Tele.log("actualización: pantalla de confirmar abierta")
        } catch (e: Exception) {
            Tele.log("no pude abrir la pantalla de confirmar: ${e.javaClass.simpleName}: ${e.message}")
        }
    }
}
