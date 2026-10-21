package ar.elroso.domotica.tele.core

import java.net.URLEncoder

/** Las direcciones del CT, armadas sobre la base de la casa. */
class TeleUrls(base: String) {
    private val root = base.trimEnd('/')

    val setup = "$root/api/tele/setup"
    val hello = "$root/api/tele/hello"
    val kiosk = "$root/pantalla?ver=1"

    fun poll(alias: String) = "$root/api/tele/${segment(alias)}/poll"

    private fun segment(text: String) = URLEncoder.encode(text, "UTF-8").replace("+", "%20")
}
