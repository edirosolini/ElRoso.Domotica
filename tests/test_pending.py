"""La conversación a medio armar, guardada.

Vive en SQLite y no en memoria por lo mismo que el silencio a pedido: un
reinicio en medio de "¿a qué hora?" dejaría la respuesta sin a dónde volver.
"""

from datetime import datetime, timedelta

from homeauto.pending import TTL, Conversation, PendingStore

CHAT = 42
OTRO = 99
NOW = datetime(2026, 9, 4, 10, 0)


def build(tmp_path, now=NOW):
    clock = lambda: now  # noqa: E731
    store = PendingStore(tmp_path / "jobs.db")
    return Conversation(store, clock=clock), store


def test_nothing_pending_is_none(tmp_path):
    talk, _ = build(tmp_path)
    assert talk.get(CHAT) is None


def test_what_was_remembered_comes_back(tmp_path):
    talk, _ = build(tmp_path)
    talk.remember(CHAT, "alarma", "creá una alarma", ("hora",))

    pending = talk.get(CHAT)
    assert pending.command == "alarma"
    assert pending.thread == "creá una alarma"
    assert pending.asked == ("hora",)


def test_remembering_again_replaces_the_previous_one(tmp_path):
    talk, _ = build(tmp_path)
    talk.remember(CHAT, "alarma", "creá una alarma", ("hora",))
    talk.remember(CHAT, "alarma", "creá una alarma\na las 7", ("hora", "mensaje"))

    assert talk.get(CHAT).asked == ("hora", "mensaje")


def test_one_chat_does_not_see_another(tmp_path):
    talk, _ = build(tmp_path)
    talk.remember(CHAT, "alarma", "creá una alarma", ("hora",))

    assert talk.get(OTRO) is None


def test_forgetting_leaves_nothing(tmp_path):
    talk, _ = build(tmp_path)
    talk.remember(CHAT, "alarma", "creá una alarma", ("hora",))
    talk.forget(CHAT)

    assert talk.get(CHAT) is None


def test_it_expires_on_its_own(tmp_path):
    """Sin vencimiento, un «sí» de mañana contesta la pregunta de hoy."""
    store = PendingStore(tmp_path / "jobs.db")
    moment = [NOW]
    talk = Conversation(store, clock=lambda: moment[0])
    talk.remember(CHAT, "alarma", "creá una alarma", ("hora",))

    moment[0] = NOW + TTL + timedelta(seconds=1)
    assert talk.get(CHAT) is None


def test_it_survives_a_restart(tmp_path):
    """Otra instancia del store sobre el mismo archivo lo sigue viendo."""
    talk, _ = build(tmp_path)
    talk.remember(CHAT, "alarma", "creá una alarma", ("hora",))

    otra = Conversation(PendingStore(tmp_path / "jobs.db"), clock=lambda: NOW)
    assert otra.get(CHAT).command == "alarma"


def test_an_expired_one_is_deleted_not_just_hidden(tmp_path):
    store = PendingStore(tmp_path / "jobs.db")
    moment = [NOW]
    talk = Conversation(store, clock=lambda: moment[0])
    talk.remember(CHAT, "alarma", "creá una alarma", ("hora",))

    moment[0] = NOW + TTL + timedelta(seconds=1)
    talk.get(CHAT)

    moment[0] = NOW
    assert store.get(CHAT) is None


def test_the_table_is_created_on_a_fresh_file(tmp_path):
    """Un despliegue nuevo no necesita migración, como las otras seis tablas."""
    store = PendingStore(tmp_path / "sub" / "jobs.db")
    assert store.get(CHAT) is None


def test_a_corrupt_row_reads_as_nothing_pending(tmp_path):
    """Antes reventar el mensaje siguiente que arrastrar una fila ilegible."""
    store = PendingStore(tmp_path / "jobs.db")
    with store._connect() as conn:
        conn.execute(
            "INSERT INTO pending (chat_id, command, thread, asked, asked_at) "
            "VALUES (?, 'alarma', 'creá una alarma', 'hora', 'cualquier cosa')",
            (CHAT,),
        )

    assert store.get(CHAT) is None
