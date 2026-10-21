package ar.elroso.domotica.tele

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.IBinder
import ar.elroso.domotica.tele.core.Heartbeat
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.TimeUnit

/** Servicio en primer plano que registra la tele en el CT y late según `BeatSchedule`. */
class TeleService : Service() {

    companion object {
        private const val CHANNEL = "tele"
        private const val NOTIFICATION_ID = 1

        /** Arranca el servicio; lanza si el sistema no lo permite desde donde se llama. */
        fun start(context: Context) {
            context.startForegroundService(Intent(context, TeleService::class.java))
        }
    }

    private var executor: ScheduledExecutorService? = null
    private var foreground = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        goForeground()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (!foreground) return START_NOT_STICKY
        if (executor != null) return START_STICKY
        val heartbeat = Heartbeat.forChoice(
            choice = Tele.choice(this),
            api = Tele.api,
            version = Tele.version,
            caps = { Tele.caps(this) },
            log = Tele::log,
        )
        if (heartbeat == null) {
            Tele.log("servicio sin tele elegida: no late")
            stopSelf()
            return START_NOT_STICKY
        }
        Tele.log("servicio arrancado, versión ${Tele.version.name}")
        val beats = Executors.newSingleThreadScheduledExecutor()
        executor = beats
        beats.execute(object : Runnable {
            override fun run() {
                val delay = try {
                    heartbeat.tick()
                } catch (e: Exception) {
                    Tele.log("el latido falló: ${e.javaClass.simpleName}: ${e.message}")
                    60_000L
                }
                if (!beats.isShutdown) beats.schedule(this, delay, TimeUnit.MILLISECONDS)
            }
        })
        return START_STICKY
    }

    override fun onTimeout(startId: Int) {
        Tele.log("el sistema venció el servicio en primer plano")
        super.onTimeout(startId)
    }

    override fun onDestroy() {
        Tele.log("servicio detenido")
        executor?.shutdownNow()
        executor = null
        super.onDestroy()
    }

    /** Pasa a primer plano con su notificación; deja logueado si el sistema lo niega. */
    private fun goForeground() {
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL, getString(R.string.app_name), NotificationManager.IMPORTANCE_LOW)
        )
        val open = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE
        )
        val notification = Notification.Builder(this, CHANNEL)
            .setContentTitle(getString(R.string.app_name))
            .setContentText("Conectada con la casa")
            .setSmallIcon(android.R.drawable.ic_lock_idle_alarm)
            .setContentIntent(open)
            .setOngoing(true)
            .build()
        try {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK)
            foreground = true
        } catch (e: Exception) {
            Tele.log("el sistema no dejó pasar a primer plano: ${e.javaClass.simpleName}: ${e.message}")
            stopSelf()
        }
    }
}
