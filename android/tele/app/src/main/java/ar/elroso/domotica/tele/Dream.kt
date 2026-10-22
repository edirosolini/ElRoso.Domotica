package ar.elroso.domotica.tele

import android.os.Handler
import android.os.Looper
import ar.elroso.domotica.tele.core.DreamDecision
import ar.elroso.domotica.tele.core.DreamPolicy
import java.lang.ref.WeakReference

/** El puente con el protector de pantalla activo: si está, qué dice la política y cómo cortarlo. */
object Dream {
    private val main = Handler(Looper.getMainLooper())

    @Volatile
    private var view: WeakReference<KioskDream>? = null

    /** Si la casa está callada, según el último `poll`. */
    @Volatile
    var quiet = false

    /** Si hay un cartel de recordatorio en pantalla; lo fija el servicio. */
    @Volatile
    var reminder: () -> Boolean = { false }

    /** Si el protector de la casa está en pantalla. */
    val active: Boolean get() = view?.get() != null

    fun attach(dream: KioskDream) {
        view = WeakReference(dream)
    }

    fun detach(dream: KioskDream) {
        if (view?.get() === dream) view = null
    }

    /** Lo que dice `DreamPolicy` con la alarma, el cartel y el silencio de ahora. */
    fun decision(): DreamDecision = DreamPolicy.decide(Kiosk.alarm, reminder(), quiet)

    /** Corta el protector, si está en pantalla. */
    fun stop(why: String) {
        val dream = view?.get() ?: return
        Tele.log("protector: lo corto, $why")
        main.post { dream.finish() }
    }
}
