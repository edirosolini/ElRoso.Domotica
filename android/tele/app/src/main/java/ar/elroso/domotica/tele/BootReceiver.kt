package ar.elroso.domotica.tele

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Al prender la tele o al actualizarse la app arranca el servicio, si ya se eligió qué tele es. */
class BootReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        val event = when (intent.action) {
            Intent.ACTION_BOOT_COMPLETED -> "arranque del equipo"
            Intent.ACTION_MY_PACKAGE_REPLACED -> "app actualizada a la ${Tele.version.name}"
            else -> return
        }
        if (!Tele.choice(context).ready) {
            Tele.log("$event sin tele elegida: el servicio no arranca")
            return
        }
        try {
            TeleService.start(context)
            Tele.log("$event: servicio pedido")
        } catch (e: Exception) {
            Tele.log("el sistema rechazó arrancar el servicio ($event): ${e.javaClass.simpleName}: ${e.message}")
        }
    }
}
