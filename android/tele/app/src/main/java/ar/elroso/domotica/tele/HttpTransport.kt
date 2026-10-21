package ar.elroso.domotica.tele

import ar.elroso.domotica.tele.core.ApkSource
import ar.elroso.domotica.tele.core.HttpReply
import ar.elroso.domotica.tele.core.Transport
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/** El transporte real hacia el CT, bloqueante: se llama fuera del hilo principal. */
class HttpTransport(private val timeoutMs: Int = 10_000) : Transport, ApkSource {

    override fun get(url: String): HttpReply = request(url, "GET", null)

    override fun fetch(url: String, target: File, limit: Long) {
        val connection = URL(url).openConnection() as HttpURLConnection
        try {
            connection.connectTimeout = timeoutMs
            connection.readTimeout = timeoutMs
            val status = connection.responseCode
            if (status != 200) throw IOException("HTTP $status")
            connection.inputStream.use { input ->
                target.outputStream().use { output ->
                    val buffer = ByteArray(64 * 1024)
                    var total = 0L
                    while (true) {
                        val read = input.read(buffer)
                        if (read < 0) break
                        total += read
                        if (total > limit) throw IOException("el APK pasa de $limit bytes")
                        output.write(buffer, 0, read)
                    }
                }
            }
        } finally {
            connection.disconnect()
        }
    }

    override fun postJson(url: String, body: String): HttpReply = request(url, "POST", body)

    private fun request(url: String, method: String, body: String?): HttpReply {
        val connection = URL(url).openConnection() as HttpURLConnection
        try {
            connection.requestMethod = method
            connection.connectTimeout = timeoutMs
            connection.readTimeout = timeoutMs
            connection.setRequestProperty("Accept", "application/json")
            if (body != null) {
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json")
                connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            }
            val status = connection.responseCode
            val stream = if (status >= 400) connection.errorStream else connection.inputStream
            val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() } ?: ""
            return HttpReply(status, text)
        } finally {
            connection.disconnect()
        }
    }
}
