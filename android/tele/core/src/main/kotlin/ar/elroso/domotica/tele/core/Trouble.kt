package ar.elroso.domotica.tele.core

/** Por qué no se pudo hablar con la casa, con el texto que ve la familia. */
enum class Trouble(val text: String) {
    NO_HOUSE("No encuentro la casa. Revisá que la tele tenga WiFi."),
    HOUSE_FAILED("La casa no pudo hacerlo. Probá de nuevo en un rato."),
}
