package ar.elroso.domotica.tele

import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import ar.elroso.domotica.tele.core.Person
import ar.elroso.domotica.tele.core.TeleChoice
import ar.elroso.domotica.tele.core.TeleFailure
import kotlin.concurrent.thread

/** Primer uso: se elige con el control qué tele es y de quién, con lo que manda `setup`. */
class SetupActivity : Activity() {

    private lateinit var title: TextView
    private lateinit var options: LinearLayout

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(buildLayout())
        load()
    }

    /** Pide `setup` al CT fuera del hilo principal y muestra las teles. */
    private fun load() {
        show("Buscando la casa…")
        thread(name = "tele-setup") {
            val result = try {
                Result.success(Tele.api.setup())
            } catch (e: TeleFailure) {
                Result.failure(e)
            }
            runOnUiThread {
                if (isDestroyed) return@runOnUiThread
                result.fold(
                    onSuccess = { chooseDevice(it.devices, it.people) },
                    onFailure = {
                        Tele.log("no pude leer la configuración del CT: ${it.message}")
                        show("No pude hablar con la casa (${it.message}).", "Reintentar" to { load() })
                    },
                )
            }
        }
    }

    private fun chooseDevice(devices: List<String>, people: List<Person>) {
        if (devices.isEmpty()) {
            show("La casa no tiene teles con pantalla.", "Reintentar" to { load() })
            return
        }
        show("¿Qué tele es esta?", *devices.map { alias -> alias to { choosePerson(alias, people) } }.toTypedArray())
    }

    private fun choosePerson(alias: String, people: List<Person>) {
        if (people.isEmpty()) {
            finishSetup(TeleChoice(alias, null))
            return
        }
        show(
            "¿De quién es la tele $alias?",
            *people.map { person -> person.name to { finishSetup(TeleChoice(alias, person.chatId)) } }.toTypedArray(),
        )
    }

    /** Guarda la elección, arranca el servicio y pasa al kiosco. */
    private fun finishSetup(choice: TeleChoice) {
        Tele.save(this, choice)
        Tele.log("primer uso: tele ${choice.alias}, persona ${if (choice.chatId == null) "sin elegir" else "elegida"}")
        try {
            TeleService.start(this)
        } catch (e: Exception) {
            Tele.log("no pude arrancar el servicio: ${e.javaClass.simpleName}: ${e.message}")
        }
        startActivity(Intent(this, MainActivity::class.java))
        finish()
    }

    /** Muestra el título y un botón por opción, con el foco en el primero. */
    private fun show(text: String, vararg choices: Pair<String, () -> Unit>) {
        title.text = text
        options.removeAllViews()
        choices.forEach { (label, action) ->
            options.addView(Button(this).apply {
                this.text = label
                textSize = 22f
                isAllCaps = false
                isFocusable = true
                setOnClickListener { action() }
                layoutParams = LinearLayout.LayoutParams(dp(420), dp(80)).apply { bottomMargin = dp(12) }
            })
        }
        options.getChildAt(0)?.requestFocus()
    }

    private fun buildLayout(): View {
        val pad = dp(48)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad, pad, pad)
            setBackgroundColor(Color.rgb(0x1E, 0x2A, 0x38))
        }
        title = TextView(this).apply {
            setTextColor(Color.WHITE)
            textSize = 30f
            setPadding(0, 0, 0, dp(24))
        }
        root.addView(title)
        options = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        root.addView(ScrollView(this).apply { addView(options) })
        return root
    }

    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()
}
