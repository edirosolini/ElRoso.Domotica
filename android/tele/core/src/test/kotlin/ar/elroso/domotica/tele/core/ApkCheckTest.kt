package ar.elroso.domotica.tele.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.security.MessageDigest

class ApkCheckTest {

    @get:Rule
    val folder = TemporaryFolder()

    private val bytes = "una apk de prueba".toByteArray()
    private val sha = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

    private fun file() = folder.newFile("tele.apk").apply { writeBytes(bytes) }

    @Test
    fun aMatchingFilePasses() {
        assertNull(ApkCheck.verify(file(), Release(6, "0.3.0", sha, bytes.size.toLong())))
    }

    @Test
    fun aWrongSizeFails() {
        assertEquals(
            "tamaño ${bytes.size}, se esperaba 99",
            ApkCheck.verify(file(), Release(6, "0.3.0", sha, 99)),
        )
    }

    @Test
    fun aWrongHashFails() {
        assertEquals(
            "el sha256 no coincide",
            ApkCheck.verify(file(), Release(6, "0.3.0", "00".repeat(32), bytes.size.toLong())),
        )
    }

    @Test
    fun aMissingFileFails() {
        assertEquals(
            "no hay archivo",
            ApkCheck.verify(folder.root.resolve("nada.apk"), Release(6, "0.3.0", sha, 1)),
        )
    }
}
