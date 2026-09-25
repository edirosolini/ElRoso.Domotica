"""El aviso al dueño cuando le escribe al bot alguien que no está en la lista."""

from datetime import datetime

from homeauto.strangers import Strangers, StrangerStore

from tests.conftest import make_config

OWNER = 42
OTHER_OWNER = 43
NEWCOMER = 12345
NOW = datetime(2026, 9, 25, 10, 0)


def build(tmp_path, allowed=(OWNER,), fail_for=()):
    sent = []

    def notify(chat_id, text):
        if chat_id in fail_for:
            raise RuntimeError("telegram caído")
        sent.append((chat_id, text))

    strangers = Strangers(
        config=make_config(allowed=allowed),
        store=StrangerStore(tmp_path / "jobs.db"),
        notify=notify,
        clock=lambda: NOW,
    )
    return strangers, sent


def test_someone_in_the_list_is_not_announced(tmp_path):
    strangers, sent = build(tmp_path)

    strangers.knock(OWNER, "Ezequiel")

    assert sent == []


def test_a_newcomer_is_announced_to_the_owner_with_its_id(tmp_path):
    strangers, sent = build(tmp_path)

    strangers.knock(NEWCOMER, "Diego (@diego)")

    chat_id, text = sent[0]
    assert chat_id == OWNER
    assert "Diego (@diego)" in text
    assert str(NEWCOMER) in text


def test_the_announcement_carries_the_line_to_paste(tmp_path):
    strangers, sent = build(tmp_path, allowed=(OWNER, OTHER_OWNER))

    strangers.knock(NEWCOMER, "Diego")

    assert f"ALLOWED_CHAT_IDS={OWNER},{OTHER_OWNER},{NEWCOMER}" in sent[0][1]
    assert "reinici" in sent[0][1]


def test_every_owner_hears_about_it(tmp_path):
    strangers, sent = build(tmp_path, allowed=(OWNER, OTHER_OWNER))

    strangers.knock(NEWCOMER, "Diego")

    assert sorted(chat_id for chat_id, _ in sent) == [OWNER, OTHER_OWNER]


def test_a_newcomer_is_announced_only_once(tmp_path):
    strangers, sent = build(tmp_path)

    strangers.knock(NEWCOMER, "Diego")
    strangers.knock(NEWCOMER, "Diego")

    assert len(sent) == 1


def test_once_survives_a_restart(tmp_path):
    first, _ = build(tmp_path)
    first.knock(NEWCOMER, "Diego")

    again, sent = build(tmp_path)
    again.knock(NEWCOMER, "Diego")

    assert sent == []


def test_an_announcement_that_reached_nobody_is_tried_again(tmp_path):
    strangers, _ = build(tmp_path, fail_for=(OWNER,))
    strangers.knock(NEWCOMER, "Diego")

    retry, sent = build(tmp_path)
    retry.knock(NEWCOMER, "Diego")

    assert len(sent) == 1


def test_one_owner_failing_does_not_silence_the_other(tmp_path):
    strangers, sent = build(tmp_path, allowed=(OWNER, OTHER_OWNER), fail_for=(OWNER,))

    strangers.knock(NEWCOMER, "Diego")

    assert [chat_id for chat_id, _ in sent] == [OTHER_OWNER]


def test_an_open_bot_has_nobody_to_tell(tmp_path):
    """Sin lista blanca todos entran: no hay extraños ni dueño a quien avisar."""
    strangers, sent = build(tmp_path, allowed=())

    strangers.knock(NEWCOMER, "Diego")

    assert sent == []


def test_the_store_remembers_when_it_was_told(tmp_path):
    store = StrangerStore(tmp_path / "jobs.db")

    store.remember(NEWCOMER, "Diego", NOW)

    assert store.known(NEWCOMER)
    assert not store.known(OWNER)
