package ar.elroso.domotica.tele

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Al prender la tele arranca el servicio, si ya se eligió qué tele es. */
class BootReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        if (!Tele.choice(context).ready) {
            Tele.log("arranque del equipo sin tele elegida: el servicio no arranca")
            return
        }
        try {
            TeleService.start(context)
            Tele.log("arranque del equipo: servicio pedido")
        } catch (e: Exception) {
            Tele.log("el sistema rechazó arrancar el servicio al prender: ${e.javaClass.simpleName}: ${e.message}")
        }
    }
}
