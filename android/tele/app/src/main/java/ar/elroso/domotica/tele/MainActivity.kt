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
import android.widget.Button
import android.widget.FrameLayout
import android.widget.TextView
import ar.elroso.domotica.tele.core.AlarmKey
import ar.elroso.domotica.tele.core.Caller
import ar.elroso.domotica.tele.core.CommandResult
import kotlin.concurrent.thread

/** El kiosco de la casa en un WebView, con la vista de alarma y su OK; manda al primer uso si falta elegir la tele. */
class MainActivity : Activity() {

    companion object {
        /** La página que el servicio pide mostrar al ponerla adelante. */
        const val EXTRA_URL = "url"
        // Opacidad del botón de cambiar la tele cuando no tiene el foco.
        private const val IDLE_ALPHA = 0.3f
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
    private var change: Button? = null

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
        change = Button(this).apply {
            text = getString(R.string.change_tele)
            isAllCaps = false
            alpha = IDLE_ALPHA
            setOnFocusChangeListener { view, focused -> view.alpha = if (focused) 1f else IDLE_ALPHA }
            setOnClickListener { startActivity(Intent(this@MainActivity, SetupActivity::class.java)) }
        }
        setContentView(FrameLayout(this).apply {
            addView(web)
            addView(hint, FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT,
                FrameLayout.LayoutParams.WRAP_CONTENT,
                Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL,
            ).apply { bottomMargin = 48 })
            addView(change, FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT,
                FrameLayout.LayoutParams.WRAP_CONTENT,
                Gravity.BOTTOM or Gravity.END,
            ).apply { setMargins(0, 0, 24, 24) })
        })
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

    /** Una alarma nueva carga su vista; el aviso del OK sigue a la alarma. */
    fun onAlarm(id: Long?) = runOnUiThread {
        if (id != null) {
            load(Tele.urls.alarm(id))
            if (Tele.choice(this).caller == null) Tele.log("alarma sin persona elegida: el OK no la apaga")
        }
        refreshHint()
    }

    private fun refreshHint() {
        val command = AlarmKey.offCommand(Kiosk.alarm, Tele.choice(this).caller)
        hint?.visibility = if (command == null) View.GONE else View.VISIBLE
    }

    /** Abajo desde el kiosco va al botón de cambiar; con una alarma sonando, el OK la apaga a nombre de quien se eligió. */
    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        if (event.keyCode == KeyEvent.KEYCODE_DPAD_DOWN && web?.hasFocus() == true) {
            if (event.action == KeyEvent.ACTION_DOWN) change?.requestFocus()
            return true
        }
        if (event.keyCode !in OK_KEYS) return super.dispatchKeyEvent(event)
        val caller = Tele.choice(this).caller
        val command = AlarmKey.offCommand(Kiosk.alarm, caller) ?: return super.dispatchKeyEvent(event)
        if (caller != null && event.action == KeyEvent.ACTION_UP && event.repeatCount == 0) silence(caller, command)
        return true
    }

    private fun silence(caller: Caller, command: String) {
        Tele.log("OK del control: $command")
        thread(name = "tele-ok") {
            when (val result = Tele.api.command(caller, command)) {
                is CommandResult.Replied -> Tele.log("el CT contestó al OK: ${result.text}")
                is CommandResult.Failed -> Tele.log("el OK no llegó al CT: ${result.reason}")
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
