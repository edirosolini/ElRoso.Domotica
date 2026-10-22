package ar.elroso.domotica.tele

import android.content.Context
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.text.TextUtils
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import ar.elroso.domotica.tele.core.Caller
import ar.elroso.domotica.tele.core.CommandResult
import ar.elroso.domotica.tele.core.Reminder
import ar.elroso.domotica.tele.core.ReminderBoard
import ar.elroso.domotica.tele.core.ReminderKey
import ar.elroso.domotica.tele.core.TeleApi
import kotlin.concurrent.thread

/** El cartel del recordatorio encima de cualquier app: tarjeta centrada sobre el fondo oscurecido, con su OK. */
class ReminderOverlay(
    private val context: Context,
    private val api: TeleApi,
    private val caller: () -> Caller?,
) {
    companion object {
        private val OK_KEYS = setOf(KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER, KeyEvent.KEYCODE_NUMPAD_ENTER)
        // Cuánto queda «✅ Hecho» antes de irse.
        private const val DONE_MS = 1_000L
        private const val DIM_ALPHA = 0x99
        private const val CARD_WIDTH = 0.6f
        private const val CARD_COLOR = 0xFF1E2A38.toInt()
        private const val MUTED_COLOR = 0xFFC9D1D9.toInt()
    }

    private val main = Handler(Looper.getMainLooper())
    private val windows = context.getSystemService(WindowManager::class.java)
    private val board = ReminderBoard()
    private var root: View? = null
    private var status: TextView? = null
    private var shown: Reminder? = null
    private var sending = false
    private var closing = false
    private var refused: Reminder? = null

    /** Si hay un cartel en pantalla; se lee desde cualquier hilo. */
    @Volatile
    var visible = false
        private set

    /** Anota la lista del `poll` y actualiza el cartel. */
    fun remindersChanged(list: List<Reminder>) {
        main.post {
            board.reminders(list)
            render()
        }
    }

    /** Anota la alarma del `poll`: con alarma no hay cartel. */
    fun alarmChanged(id: Long?) {
        main.post {
            board.alarm(id)
            render()
        }
    }

    /** Saca el cartel, si hay. */
    fun close() {
        main.post { remove() }
    }

    private fun render() {
        if (closing) return
        val card = board.card
        if (card == shown) return
        val current = shown
        if (card != null && sending && current != null && current.id == card.id) {
            shown = card
            return
        }
        remove()
        if (card == null) return
        if (!Settings.canDrawOverlays(context)) {
            if (card != refused) Tele.log("recordatorio ${card.id} sin permiso de superposición: no se muestra")
            refused = card
            return
        }
        show(card)
    }

    private fun show(card: Reminder) {
        val density = context.resources.displayMetrics.density
        val who = caller()
        val content = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            background = GradientDrawable().apply {
                setColor(CARD_COLOR)
                cornerRadius = 24 * density
            }
            val side = (48 * density).toInt()
            val top = (36 * density).toInt()
            setPadding(side, top, side, top)
        }
        content.addView(text(card.message, 40f, Color.WHITE).apply {
            maxLines = 2
            ellipsize = TextUtils.TruncateAt.END
            typeface = Typeface.DEFAULT_BOLD
        })
        card.forName?.let { content.addView(text(context.getString(R.string.reminder_for, it), 28f, MUTED_COLOR), spaced(density)) }
        val line = if (who == null) null else text(context.getString(R.string.reminder_ok), 26f, MUTED_COLOR)
        line?.let { content.addView(it, spaced(density)) }
        val frame = object : FrameLayout(context) {
            override fun dispatchKeyEvent(event: KeyEvent): Boolean = onKey(event)
        }.apply {
            setBackgroundColor(Color.argb(DIM_ALPHA, 0, 0, 0))
            isFocusable = true
            isFocusableInTouchMode = true
            addView(content, FrameLayout.LayoutParams(
                (context.resources.displayMetrics.widthPixels * CARD_WIDTH).toInt(),
                ViewGroup.LayoutParams.WRAP_CONTENT,
                Gravity.CENTER,
            ))
        }
        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
            PixelFormat.TRANSLUCENT,
        ).apply { gravity = Gravity.CENTER }
        Dream.stop("hay un recordatorio")
        try {
            windows.addView(frame, params)
        } catch (e: Exception) {
            Tele.log("no pude mostrar el recordatorio ${card.id}: ${e.javaClass.simpleName}: ${e.message}")
            return
        }
        frame.requestFocus()
        root = frame
        status = line
        shown = card
        visible = true
        Tele.log("recordatorio en pantalla: ${card.id} (re-avisos ${card.nags})")
    }

    private fun text(value: String, size: Float, color: Int) = TextView(context).apply {
        text = value
        textSize = size
        setTextColor(color)
        gravity = Gravity.CENTER
    }

    private fun spaced(density: Float) = LinearLayout.LayoutParams(
        ViewGroup.LayoutParams.WRAP_CONTENT,
        ViewGroup.LayoutParams.WRAP_CONTENT,
    ).apply { topMargin = (16 * density).toInt() }

    /** El OK marca hecho; cualquier otra tecla que llegue cierra el cartel hasta el próximo re-aviso. */
    private fun onKey(event: KeyEvent): Boolean {
        val card = shown ?: return false
        if (closing || event.action != KeyEvent.ACTION_UP || event.repeatCount != 0) return true
        if (event.keyCode in OK_KEYS) {
            ok(card)
        } else {
            Tele.log("recordatorio ${card.id} cerrado con la tecla ${KeyEvent.keyCodeToString(event.keyCode)}")
            board.dismiss(card)
            render()
        }
        return true
    }

    private fun ok(card: Reminder) {
        if (sending) return
        val who = caller()
        val command = ReminderKey.doneCommand(card, who)
        if (who == null || command == null) {
            Tele.log("recordatorio ${card.id} sin persona elegida: el OK solo cierra")
            board.dismiss(card)
            render()
            return
        }
        Tele.log("OK del control: $command")
        sending = true
        status?.text = context.getString(R.string.reminder_waiting)
        thread(name = "tele-reminder") {
            val result = api.command(who, command)
            main.post { finish(card, result) }
        }
    }

    private fun finish(card: Reminder, result: CommandResult) {
        sending = false
        val here = shown?.id == card.id
        when (result) {
            is CommandResult.Replied -> {
                Tele.log("el CT contestó al hecho ${card.id}: ${result.text}")
                board.done(card.id)
                if (!here) return render()
                status?.text = context.getString(R.string.reminder_done)
                closing = true
                main.postDelayed({
                    closing = false
                    render()
                }, DONE_MS)
            }
            is CommandResult.Failed -> {
                Tele.log("el hecho ${card.id} no llegó al CT: ${result.reason}")
                if (here) status?.text = context.getString(R.string.reminder_failed, result.reason)
            }
        }
    }

    private fun remove() {
        val view = root
        root = null
        status = null
        shown = null
        visible = false
        if (view == null) return
        try {
            windows.removeView(view)
        } catch (e: Exception) {
            Tele.log("no pude sacar el recordatorio: ${e.javaClass.simpleName}: ${e.message}")
        }
    }
}
