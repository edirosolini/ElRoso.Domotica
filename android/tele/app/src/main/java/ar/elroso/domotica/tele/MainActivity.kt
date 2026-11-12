package ar.elroso.domotica.tele

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.TextView
import ar.elroso.domotica.tele.core.AlarmKey
import ar.elroso.domotica.tele.core.CommandResult
import ar.elroso.domotica.tele.core.OkKey
import kotlin.concurrent.thread

/** El kiosco de la casa en un WebView, con la vista de alarma y su OK; manda al primer uso si falta elegir la tele. */
class MainActivity : Activity() {

    companion object {
        /** La página que el servicio pide mostrar al ponerla adelante. */
        const val EXTRA_URL = "url"
        private val OK_KEYS = setOf(KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER, KeyEvent.KEYCODE_NUMPAD_ENTER)
    }

    /** Permisos que la app pide, en este orden. */
    private enum class Permission(val label: String) {
        NOTIFICATIONS("notificaciones"),
        OVERLAY("mostrar sobre otras apps"),
        INSTALL("instalar apps desconocidas"),
    }

    private val asked = mutableSetOf<Permission>()
    private var web: WebView? = null
    private var hint: TextView? = null
    private val okKey = OkKey()
    private val alarmKey = AlarmKey()
    private var notice: String? = null
    private var sticky = false
    private val clearNotice = Runnable {
        notice = null
        refreshHint()
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!Tele.choice(this).ready) {
            startActivity(Intent(this, SetupActivity::class.java))
            finish()
            return
        }
        try {
            TeleService.start(this)
        } catch (e: Exception) {
            Tele.log("no pude arrancar el servicio: ${e.javaClass.simpleName}: ${e.message}")
        }
        web = WebView(this).apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            webViewClient = object : WebViewClient() {
                override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                    if (request.isForMainFrame) Tele.log("el kiosco no cargó: ${error.errorCode} ${error.description}")
                }
            }
            loadUrl(intent.getStringExtra(EXTRA_URL) ?: Tele.urls.kiosk)
        }
        hint = TextView(this).apply {
            text = getString(R.string.ok_to_silence)
            textSize = 28f
            setTextColor(Color.WHITE)
            setBackgroundColor(Color.argb(0xB0, 0, 0, 0))
            setPadding(48, 16, 48, 16)
            visibility = View.GONE
        }
        setContentView(FrameLayout(this).apply {
            addView(web)
            addView(hint, FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT,
                FrameLayout.LayoutParams.WRAP_CONTENT,
                Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL,
            ).apply { bottomMargin = 48 })
        })
        alarmKey.alarm(Kiosk.alarm)
        Kiosk.attach(this)
        refreshHint()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        intent.getStringExtra(EXTRA_URL)?.let { load(it) }
    }

    /** Carga la página si no es la que ya se ve. */
    fun load(url: String) = runOnUiThread {
        val view = web ?: return@runOnUiThread
        if (view.url != url) view.loadUrl(url)
    }

    /** Vuelve al kiosco y deja de estar adelante. */
    fun leave() = runOnUiThread {
        web?.loadUrl(Tele.urls.kiosk)
        moveTaskToBack(true)
    }

    /** Una alarma nueva carga su vista; el aviso del OK sigue a la alarma y una falla anterior se borra. */
    fun onAlarm(id: Long?) = runOnUiThread {
        alarmKey.alarm(id)
        if (sticky) showNotice(null)
        if (id != null) {
            load(Tele.urls.alarm(id))
            if (Tele.choice(this).caller == null) Tele.log("alarma sin persona elegida: el OK no la apaga")
        }
        refreshHint()
    }

    /** Abajo, el aviso del momento o «OK = 🔕 Apagar alarma» mientras suena una alarma que este OK puede apagar. */
    private fun refreshHint() {
        val view = hint ?: return
        val off = AlarmKey.offCommand(Kiosk.alarm, Tele.choice(this).caller) != null && !alarmKey.silenced
        val text = notice ?: if (off) getString(R.string.ok_to_silence) else null
        if (text != null) view.text = text
        view.visibility = if (text == null) View.GONE else View.VISIBLE
    }

    /** Muestra un aviso abajo; con duración se va solo, sin ella queda hasta el próximo OK. */
    private fun showNotice(text: String?, durationMs: Long? = null) {
        hint?.removeCallbacks(clearNotice)
        notice = text
        sticky = text != null && durationMs == null
        if (text != null && durationMs != null) hint?.postDelayed(clearNotice, durationMs)
        refreshHint()
    }

    /** Todo OK se consume: con alarma, soltarlo la apaga; sin alarma, mantenerlo tres segundos abre el cambio de tele o persona. */
    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        if (event.keyCode !in OK_KEYS) return super.dispatchKeyEvent(event)
        val alarm = Kiosk.alarm != null
        val action = when (event.action) {
            KeyEvent.ACTION_DOWN -> okKey.down(event.eventTime, event.repeatCount > 0, alarm)
            KeyEvent.ACTION_UP -> okKey.up(event.eventTime, alarm)
            else -> OkKey.Action.NONE
        }
        when (action) {
            OkKey.Action.SILENCE -> silence()
            OkKey.Action.CHANGE -> change()
            OkKey.Action.NONE -> Unit
        }
        return true
    }

    private fun change() {
        Tele.log("OK mantenido: cambiar tele o persona")
        startActivity(Intent(this, SetupActivity::class.java))
    }

    private fun silence() {
        val id = Kiosk.alarm ?: return
        val caller = Tele.choice(this).caller ?: return
        alarmKey.alarm(id)
        val command = alarmKey.press(caller) ?: return
        Tele.log("OK del control: $command")
        showNotice(null)
        thread(name = "tele-ok") {
            val result = Tele.api.command(caller, command)
            runOnUiThread { answered(id, result) }
        }
    }

    private fun answered(id: Long, result: CommandResult) {
        when (result) {
            is CommandResult.Replied -> {
                Tele.log("el CT contestó al OK: ${result.text}")
                alarmKey.answered(id, replied = true)
                showNotice(getString(R.string.alarm_silenced), AlarmKey.SILENCED_MS)
            }
            is CommandResult.Failed -> {
                Tele.log("el OK no llegó al CT: ${result.reason}")
                alarmKey.answered(id, replied = false)
                showNotice(result.trouble.text)
            }
        }
    }

    override fun onResume() {
        super.onResume()
        val view = web ?: return
        view.requestFocus()
        askNextPermission()
    }

    override fun onDestroy() {
        hint?.removeCallbacks(clearNotice)
        Kiosk.detach(this)
        web?.destroy()
        web = null
        super.onDestroy()
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        askNextPermission()
    }

    /** Pide el primer permiso que falte y no se haya pedido en esta apertura. */
    private fun askNextPermission() {
        val next = Permission.entries.firstOrNull { !granted(it) && it !in asked } ?: return
        asked += next
        Tele.log("pidiendo permiso: ${next.label}")
        when (next) {
            Permission.NOTIFICATIONS -> requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
            Permission.OVERLAY -> askOverlay()
            Permission.INSTALL -> askInstall()
        }
    }

    private fun granted(permission: Permission): Boolean = when (permission) {
        Permission.NOTIFICATIONS -> Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
        Permission.OVERLAY -> Settings.canDrawOverlays(this)
        Permission.INSTALL -> Tele.canInstall(this)
    }

    /** Abre el ajuste de superposición, o deja logueado que el equipo no lo tiene. */
    private fun askOverlay() {
        try {
            startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")))
        } catch (e: ActivityNotFoundException) {
            Tele.log("este equipo no tiene el ajuste de superposición")
        }
    }

    /** Abre el ajuste de instalar apps desconocidas, o deja logueado que el equipo no lo tiene. */
    private fun askInstall() {
        try {
            startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:$packageName")))
        } catch (e: ActivityNotFoundException) {
            Tele.log("este equipo no tiene el ajuste de instalar apps desconocidas")
        }
    }
}
