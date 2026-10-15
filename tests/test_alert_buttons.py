"""Los botones que acompañan a los avisos de vigilancia y de alarma."""

from homeauto import main


class FakeHouse:
    def __init__(self, spoken=True):
        self.spoken = spoken
        self.announced = []
        self.told = []

    def announce(self, text, urgent=False, written=None, actions=(), others=main.SAME):
        self.announced.append(actions)
        return {"spoken": self.spoken}

    def tell(self, text, others=main.SAME, actions=()):
        self.told.append(actions)


def test_a_spoken_alert_reaches_the_chat_with_its_buttons():
    house = FakeHouse(spoken=True)

    main._alert(house, "vps no responde", True, actions=main.MONITOR_ACTIONS)

    assert house.told == [main.MONITOR_ACTIONS]


def test_an_unspoken_alert_hands_its_buttons_to_the_house():
    house = FakeHouse(spoken=False)

    main._alert(house, "vps no responde", False, actions=main.MONITOR_ACTIONS)

    assert house.announced == [main.MONITOR_ACTIONS]


def test_a_monitor_alert_offers_the_status_and_a_silence():
    commands = [data for _label, data in main.MONITOR_ACTIONS]

    assert commands == ["estado", "silencio 1h"]


def test_a_seq_alert_only_offers_a_silence():
    """/estado muestra los chequeos, no Seq: ahí no ayuda."""
    assert [data for _label, data in main.SEQ_ACTIONS] == ["silencio 1h"]


def test_an_alarm_can_be_postponed_ten_or_thirty_minutes():
    assert [data for _label, data in main.SNOOZE_ACTIONS] == ["posponer 10m", "posponer 30m"]


def test_every_button_fits_in_telegram():
    """Telegram rechaza un callback_data de más de 64 bytes."""
    for actions in (main.SNOOZE_ACTIONS, main.MONITOR_ACTIONS, main.SEQ_ACTIONS):
        for _label, data in actions:
            assert len(data.encode()) <= 64


def test_an_outage_offers_to_confirm_it_besides_the_status_and_the_silence():
    actions = main._monitor_actions("vps")

    assert actions == (("✅ Confirmar", "confirmar vps"),) + main.MONITOR_ACTIONS


def test_a_recovery_has_nothing_to_confirm():
    assert main._monitor_actions("") == main.MONITOR_ACTIONS


def test_the_longest_name_a_check_may_have_fits_in_the_confirm_button():
    from homeauto.watch.loading import MAX_NAME_BYTES

    [(_label, data), *_] = main._monitor_actions("ñ" * (MAX_NAME_BYTES // 2))

    assert len(data.encode()) <= 64
    assert len(main._monitor_actions("a" * (MAX_NAME_BYTES + 1))[0][1].encode()) > 64


def test_confirm_is_a_button_and_not_something_to_route_or_type():
    from homeauto.bot.commands import Commands
    from tests.conftest import StubRegistry, make_config

    assert "confirmar" not in Commands(config=make_config(), speakers=StubRegistry())._dispatch()
    assert "confirmar" not in main.ALL_COMMANDS


class RemindHouse:
    def __init__(self, spoken=True):
        self.spoken = spoken
        self.announced = []
        self.told = []

    def announce(self, text, urgent=False, written=None, actions=(), others=main.SAME, chime=None):
        self.announced.append(
            {"text": text, "urgent": urgent, "written": written, "actions": actions,
             "others": others, "chime": chime}
        )
        return {"spoken": self.spoken}

    def tell(self, text, others=main.SAME, actions=()):
        self.told.append((text, others, actions))


def test_a_reminder_never_wakes_anyone_but_sounds_like_the_urgent_one():
    house = RemindHouse()

    main._still_down(house, "Atención: vps sigue sin responder.", "vps", "HTTP 502 en 1.2s")

    [call] = house.announced
    assert call["urgent"] is False
    assert call["chime"] == main.chime.ALARM
    assert call["others"] is None


def test_a_reminder_is_written_as_still_down_with_the_detail_and_the_confirm_button():
    house = RemindHouse(spoken=True)

    main._still_down(house, "Atención: vps sigue sin responder.", "vps", "HTTP 502 en 1.2s")

    assert house.told == [("🚨 Sigue caído: vps\nHTTP 502 en 1.2s", None, main._monitor_actions("vps"))]


def test_an_unspoken_reminder_hands_its_text_and_button_to_the_house():
    house = RemindHouse(spoken=False)

    main._still_down(house, "Atención: vps sigue sin responder.", "vps", "")

    [call] = house.announced
    assert call["written"] == "🚨 Sigue caído: vps"
    assert call["actions"] == main._monitor_actions("vps")
    assert house.told == []


def test_a_confirmation_is_told_to_the_other_alert_chats_only():
    sent = []

    main._tell_alert_chats(lambda chat, text: sent.append((chat, text)), {42, 77}, 42, "✅ hola")

    assert sent == [(77, "✅ hola")]


def test_a_chat_that_fails_does_not_stop_the_others():
    sent = []

    def notify(chat, text):
        if chat == 1:
            raise RuntimeError("caído")
        sent.append(chat)

    main._tell_alert_chats(notify, [1, 2, 3], 3, "✅ hola")

    assert sent == [2]


def test_every_button_runs_a_command_that_exists():
    from homeauto.bot.commands import Commands
    from tests.conftest import StubRegistry, make_config

    known = Commands(config=make_config(), speakers=StubRegistry())._dispatch()
    for actions in (main.SNOOZE_ACTIONS, main.MONITOR_ACTIONS, main.SEQ_ACTIONS):
        for _label, data in actions:
            assert data.split(" ")[0] in known, data
