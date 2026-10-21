package ar.elroso.domotica.tele

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient

/** El kiosco de la casa en un WebView; manda al primer uso si todavía no se eligió la tele. */
class MainActivity : Activity() {

    /** Permisos que la app pide, en este orden. */
    private enum class Permission(val label: String) {
        NOTIFICATIONS("notificaciones"),
        OVERLAY("mostrar sobre otras apps"),
    }

    private val asked = mutableSetOf<Permission>()
    private var web: WebView? = null

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
            loadUrl(Tele.urls.kiosk)
        }
        setContentView(web)
    }

    override fun onResume() {
        super.onResume()
        if (web != null) askNextPermission()
    }

    override fun onDestroy() {
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
        }
    }

    private fun granted(permission: Permission): Boolean = when (permission) {
        Permission.NOTIFICATIONS -> Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
        Permission.OVERLAY -> Settings.canDrawOverlays(this)
    }

    /** Abre el ajuste de superposición, o deja logueado que el equipo no lo tiene. */
    private fun askOverlay() {
        try {
            startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")))
        } catch (e: ActivityNotFoundException) {
            Tele.log("este equipo no tiene el ajuste de superposición")
        }
    }
}
