package ar.elroso.domotica.tele.core

import java.net.URLEncoder

/** Las direcciones del CT, armadas sobre la base de la casa. */
class TeleUrls(base: String) {
    private val root = base.trimEnd('/')

    val setup = "$root/api/tele/setup"
    val hello = "$root/api/tele/hello"
    val kiosk = "$root/pantalla?ver=1"
    val command = "$root/api/command"
    val release = "$root/app/tele.json"
    val apk = "$root/app/tele.apk"

    fun poll(alias: String) = "$root/api/tele/${segment(alias)}/poll"

    fun ack(alias: String) = "$root/api/tele/${segment(alias)}/ack"

    fun alarm(job: Long) = "$root/alarma?job=$job"

    private fun segment(text: String) = URLEncoder.encode(text, "UTF-8").replace("+", "%20")
}
