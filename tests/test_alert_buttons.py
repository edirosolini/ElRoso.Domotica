"""Los botones que acompañan a los avisos de vigilancia y de alarma."""

from homeauto import main


class FakeHouse:
    def __init__(self, spoken=True):
        self.spoken = spoken
        self.announced = []
        self.told = []

    def announce(self, text, urgent=False, written=None, actions=()):
        self.announced.append(actions)
        return {"spoken": self.spoken}

    def tell_everyone(self, text, actions=()):
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


def test_every_button_runs_a_command_that_exists():
    from homeauto.bot.commands import Commands
    from tests.conftest import StubRegistry, make_config

    known = Commands(config=make_config(), speakers=StubRegistry())._dispatch()
    for actions in (main.SNOOZE_ACTIONS, main.MONITOR_ACTIONS, main.SEQ_ACTIONS):
        for _label, data in actions:
            assert data.split(" ")[0] in known, data
