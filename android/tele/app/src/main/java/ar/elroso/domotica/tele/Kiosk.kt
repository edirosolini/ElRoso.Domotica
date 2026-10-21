package ar.elroso.domotica.tele

import java.lang.ref.WeakReference

/** El puente entre el servicio y el kiosco abierto: qué alarma suena y qué página va. */
object Kiosk {
    @Volatile
    var alarm: Long? = null
        private set

    @Volatile
    private var view: WeakReference<MainActivity>? = null

    fun attach(activity: MainActivity) {
        view = WeakReference(activity)
    }

    fun detach(activity: MainActivity) {
        if (view?.get() === activity) view = null
    }

    /** Anota la alarma del `poll` y se la pasa al kiosco abierto. */
    fun alarmChanged(id: Long?) {
        alarm = id
        view?.get()?.onAlarm(id)
    }

    /** Carga la página en el kiosco, si está abierto. */
    fun load(url: String) {
        view?.get()?.load(url)
    }

    /** Vuelve al kiosco y lo saca de adelante, si está abierto. */
    fun leave() {
        view?.get()?.leave()
    }
}
