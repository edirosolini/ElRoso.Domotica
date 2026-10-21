package ar.elroso.domotica.tele.core

import java.io.File
import java.security.MessageDigest

/** Verifica que el APK bajado sea el que publica `tele.json`. */
object ApkCheck {

    /** Null si tamaño y sha256 coinciden; si no, el motivo. */
    fun verify(file: File, release: Release): String? {
        if (!file.isFile) return "no hay archivo"
        val size = file.length()
        if (size != release.size) return "tamaño $size, se esperaba ${release.size}"
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(64 * 1024)
            while (true) {
                val read = input.read(buffer)
                if (read < 0) break
                digest.update(buffer, 0, read)
            }
        }
        val sha = digest.digest().joinToString("") { "%02x".format(it) }
        return if (sha == release.sha256) null else "el sha256 no coincide"
    }
}
