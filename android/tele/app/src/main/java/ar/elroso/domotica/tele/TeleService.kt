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
import android.os.PowerManager
import ar.elroso.domotica.tele.core.AckResult
import ar.elroso.domotica.tele.core.AckState
import ar.elroso.domotica.tele.core.Heartbeat
import ar.elroso.domotica.tele.core.Order
import ar.elroso.domotica.tele.core.OrderKind
import ar.elroso.domotica.tele.core.OrderRunner
import ar.elroso.domotica.tele.core.UpdatePolicy
import ar.elroso.domotica.tele.core.Updater
import java.io.File
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.TimeUnit

/** Servicio en primer plano que registra la tele, late según `BeatSchedule` y ejecuta las órdenes del CT. */
class TeleService : Service() {

    companion object {
        private const val CHANNEL = "tele"
        private const val NOTIFICATION_ID = 1
        // Cuándo se busca una versión nueva: al rato de arrancar y después cada hora.
        private const val UPDATE_FIRST_MS = 30_000L
        private const val UPDATE_EVERY_MS = 3_600_000L

        /** Arranca el servicio; lanza si el sistema no lo permite desde donde se llama. */
        fun start(context: Context) {
            context.startForegroundService(Intent(context, TeleService::class.java))
        }
    }

    private var executor: ScheduledExecutorService? = null
    private var player: ExecutorService? = null
    private var updates: ScheduledExecutorService? = null
    private var reminders: ReminderOverlay? = null
    private var foreground = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        goForeground()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (!foreground) return START_NOT_STICKY
        if (executor != null) return START_STICKY
        val choice = Tele.choice(this)
        val alias = choice.alias.orEmpty()
        val runner = OrderRunner(
            device = AndroidDevice(this),
            ack = { seq, state -> acknowledge(alias, seq, state) },
            log = Tele::log,
        )
        val plays = Executors.newSingleThreadExecutor()
        val overlay = ReminderOverlay(this, Tele.api) { Tele.choice(this).caller }
        val heartbeat = Heartbeat.forChoice(
            choice = choice,
            api = Tele.api,
            version = Tele.version,
            caps = { Tele.caps(this) },
            log = Tele::log,
            onAlarm = { id ->
                Kiosk.alarmChanged(id)
                overlay.alarmChanged(id)
            },
            onOrders = { orders -> orders.forEach { dispatch(it, runner, plays) } },
            onRepeated = { orders ->
                orders.forEach {
                    Tele.log("orden ${it.seq} repetida: vuelvo a confirmarla")
                    runner.resend(it)
                }
            },
            onReminders = overlay::remindersChanged,
        )
        if (heartbeat == null) {
            plays.shutdown()
            Tele.log("servicio sin tele elegida: no late")
            stopSelf()
            return START_NOT_STICKY
        }
        Tele.log("servicio arrancado, versión ${Tele.version.name}")
        val beats = Executors.newSingleThreadScheduledExecutor()
        executor = beats
        player = plays
        reminders = overlay
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
        updates = scheduleUpdates(runner, overlay)
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
        player?.shutdownNow()
        player = null
        updates?.shutdownNow()
        updates = null
        reminders?.close()
        reminders = null
        super.onDestroy()
    }

    /** Agenda la búsqueda de versiones nuevas en un hilo propio, aparte del latido. */
    private fun scheduleUpdates(runner: OrderRunner, overlay: ReminderOverlay): ScheduledExecutorService {
        val updater = Updater(
            api = Tele.api,
            urls = Tele.urls,
            policy = UpdatePolicy(Tele.version.code, Tele.offers(this)),
            source = Tele.transport,
            installer = SessionInstaller(this),
            target = File(cacheDir, "update.apk"),
            alarm = { Kiosk.alarm },
            reminder = { overlay.visible },
            playing = { runner.playing },
            awake = { getSystemService(PowerManager::class.java).isInteractive },
            allowed = { Tele.canInstall(this) },
            log = Tele::log,
        )
        val checks = Executors.newSingleThreadScheduledExecutor()
        checks.scheduleWithFixedDelay({
            try {
                updater.check()
            } catch (e: Exception) {
                Tele.log("la búsqueda de actualización falló: ${e.javaClass.simpleName}: ${e.message}")
            }
        }, UPDATE_FIRST_MS, UPDATE_EVERY_MS, TimeUnit.MILLISECONDS)
        return checks
    }

    /** Ejecuta la orden: un `play` en el hilo de reproducción, el resto en el del latido. */
    private fun dispatch(order: Order, runner: OrderRunner, plays: ExecutorService) {
        Tele.log("orden ${order.seq}: ${order.kind.name.lowercase()}")
        val run = Runnable {
            try {
                runner.run(order)
            } catch (e: Exception) {
                Tele.log("la orden ${order.seq} se rompió: ${e.javaClass.simpleName}: ${e.message}")
            }
        }
        if (order.kind == OrderKind.PLAY) plays.execute(run) else run.run()
    }

    /** Le manda al CT el `ack` de la orden y loguea si no lo aceptó o no llegó. */
    private fun acknowledge(alias: String, seq: Long, state: AckState) {
        when (val result = Tele.api.ack(alias, seq, state)) {
            is AckResult.Answered -> if (!result.accepted) Tele.log("el CT ya no esperaba la orden $seq (${state.wire})")
            is AckResult.Failed -> Tele.log("no pude confirmar la orden $seq (${state.wire}): ${result.reason}")
        }
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
