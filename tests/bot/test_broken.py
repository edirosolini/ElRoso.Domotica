"""La respuesta a una falla: llana para la familia, con el motivo para los chats de alertas."""

from homeauto.bot.commands import broken


def test_the_family_does_not_read_the_exception():
    answer = broken(RuntimeError("Address already in use"), detail=False)

    assert answer == "No me salió. Probá de nuevo en un rato."


def test_an_alert_chat_reads_the_reason():
    answer = broken(RuntimeError("Address already in use"), detail=True)

    assert answer == "🔴 No pude procesar la solicitud: Address already in use"
