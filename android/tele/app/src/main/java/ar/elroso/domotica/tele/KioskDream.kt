package ar.elroso.domotica.tele

import android.annotation.SuppressLint
import android.graphics.Color
import android.graphics.Bitmap
import android.os.Handler
import android.os.Looper
import android.service.dreams.DreamService
import android.view.Gravity
import android.view.View
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.TextView
import ar.elroso.domotica.tele.core.BeatSchedule
import ar.elroso.domotica.tele.core.DreamDecision
import kotlin.random.Random

/** El kiosco de la casa como protector de pantalla; sin conexión, un cartel que se mueve y reintenta. */
class KioskDream : DreamService() {

    companion object {
        // Cuánto tarda el cartel sin conexión en llegar a su próxima posición.
        private const val DRIFT_MS = 30_000L
    }

    private val main = Handler(Looper.getMainLooper())
    private val schedule = BeatSchedule()
    private var web: WebView? = null
    private var offline: FrameLayout? = null
    private var message: TextView? = null
    private var failed = false
    private val retry = Runnable { web?.loadUrl(Tele.urls.kiosk) }
    private val drift = object : Runnable {
        override fun run() {
            move()
            main.postDelayed(this, DRIFT_MS)
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        isInteractive = false
        isFullscreen = true
        isScreenBright = true
        val decision = Dream.decision()
        if (decision != DreamDecision.KEEP) {
            Tele.log("protector: no arranca (${decision.name.lowercase()})")
            finish()
            return
        }
        Dream.attach(this)
        Tele.log("protector: arranca")
        val page = WebView(this).apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            webViewClient = object : WebViewClient() {
                override fun onPageStarted(view: WebView, url: String?, favicon: Bitmap?) {
                    failed = false
                }

                override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                    if (request.isForMainFrame) unreachable("${error.errorCode} ${error.description}")
                }

                override fun onPageFinished(view: WebView, url: String?) {
                    if (!failed) reached()
                }
            }
        }
        val text = TextView(this).apply {
            text = getString(R.string.dream_offline)
            textSize = 28f
            setTextColor(Color.GRAY)
        }
        val black = FrameLayout(this).apply {
            setBackgroundColor(Color.BLACK)
            visibility = View.GONE
            addView(text, FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT,
                FrameLayout.LayoutParams.WRAP_CONTENT,
                Gravity.CENTER,
            ))
        }
        web = page
        offline = black
        message = text
        setContentView(FrameLayout(this).apply {
            addView(page)
            addView(black)
        })
        page.loadUrl(Tele.urls.kiosk)
    }

    override fun onDetachedFromWindow() {
        Dream.detach(this)
        main.removeCallbacksAndMessages(null)
        web?.destroy()
        web = null
        offline = null
        message = null
        Tele.log("protector: termina")
        super.onDetachedFromWindow()
    }

    /** Tapa el kiosco con el cartel sin conexión y agenda el reintento. */
    private fun unreachable(reason: String) {
        failed = true
        val delay = schedule.failed()
        Tele.log("protector: el kiosco no cargó ($reason); reintento en ${delay / 1000} s")
        if (offline?.visibility != View.VISIBLE) {
            offline?.visibility = View.VISIBLE
            main.removeCallbacks(drift)
            main.post(drift)
        }
        main.removeCallbacks(retry)
        main.postDelayed(retry, delay)
    }

    /** Saca el cartel sin conexión cuando el kiosco cargó. */
    private fun reached() {
        schedule.succeeded()
        main.removeCallbacks(drift)
        offline?.visibility = View.GONE
    }

    /** Lleva el cartel despacio a un lugar al azar de la pantalla. */
    private fun move() {
        val box = offline ?: return
        val text = message ?: return
        val x = (box.width - text.width) / 2f
        val y = (box.height - text.height) / 2f
        text.animate()
            .translationX(if (x > 0) Random.nextFloat() * 2 * x - x else 0f)
            .translationY(if (y > 0) Random.nextFloat() * 2 * y - y else 0f)
            .setDuration(DRIFT_MS)
            .start()
    }
}
