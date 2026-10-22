package ar.elroso.domotica.tele.core

/** Lee `screensaver_components` y dice si el protector elegido es el componente `pkg/cls`. */
class ScreensaverSetting(private val pkg: String, private val cls: String) {

    /** Si alguno de la lista, en forma corta `pkg/.Cls` o larga `pkg/pkg.Cls`, es el propio. */
    fun isOurs(value: String?): Boolean =
        value.orEmpty().split(',').map { it.trim() }.any { matches(it) }

    private fun matches(component: String): Boolean {
        val (owner, name) = component.split('/', limit = 2).takeIf { it.size == 2 } ?: return false
        if (owner != pkg) return false
        val full = if (name.startsWith(".")) owner + name else name
        return full == cls
    }
}
