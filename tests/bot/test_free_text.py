"""Texto libre: sin barra adelante, la casa igual entiende.

Decisión del dueño: **ejecuta y avisa qué entendió**, no pide confirmación.
Si erró, se deshace a mano — para eso está /cancelar.
"""

from homeauto.ask import Answer
from homeauto.bot.commands import Commands
from homeauto.route import Decision, RouteError

from tests.conftest import FakeSpeaker, StubRegistry, make_config

OWNER = 42
INTRUSO = 99


class FakeRouter:
    def __init__(self, decision=None, boom=None):
        self.decision = decision if decision is not None else Decision("clima")
        self.boom = boom
        self.seen = []

    def route(self, message):
        self.seen.append(message)
        if self.boom:
            raise self.boom
        return self.decision


class FakeAsker:
    def __init__(self):
        self.asked = []

    def ask(self, question):
        self.asked.append(question)
        return Answer(spoken="son dos cosas", written="Son dos cosas.")


class FakeWeather:
    def spoken(self):
        return "Ahora hay catorce grados."


def build(router=None, asker=None, **speakers):
    speakers = speakers or {"parlante": FakeSpeaker("parlante")}
    commands = Commands(
        config=make_config(allowed={OWNER}, devices=dict.fromkeys(speakers)),
        speakers=StubRegistry(**speakers),
        weather=FakeWeather(),
        asker=asker if asker is not None else FakeAsker(),
        router=router if router is not None else FakeRouter(),
    )
    return commands, speakers


def test_a_plain_message_runs_the_command_it_meant():
    cmd, spk = build(router=FakeRouter(Decision("clima")))

    reply = cmd.free_text(OWNER, "cómo viene el tiempo")

    assert spk["parlante"].said == ["Ahora hay catorce grados."]


def test_it_says_what_it_understood():
    """Ejecuta sin preguntar, así que tiene que quedar claro qué hizo."""
    cmd, _ = build(router=FakeRouter(Decision("volumen", "40")))

    reply = cmd.free_text(OWNER, "bajá el volumen a 40")

    assert "/volumen 40" in reply


def test_a_question_goes_to_the_asker():
    asker = FakeAsker()
    cmd, _ = build(router=FakeRouter(Decision(None)), asker=asker)

    reply = cmd.free_text(OWNER, "cuántos goles hizo Messi")

    assert asker.asked == ["cuántos goles hizo Messi"]
    assert "Son dos cosas." in reply


def test_the_whole_message_reaches_the_router():
    router = FakeRouter(Decision(None))
    cmd, _ = build(router=router)

    cmd.free_text(OWNER, "apagá la tele del comedor")

    assert router.seen == ["apagá la tele del comedor"]


def test_a_router_failure_does_not_become_a_web_search():
    """🔴 Mandar a buscar en internet un pedido de apagar la tele es peor que no entender."""
    asker = FakeAsker()
    cmd, _ = build(router=FakeRouter(boom=RouteError("No te entendí. Probá con /ayuda.")),
                   asker=asker)

    reply = cmd.free_text(OWNER, "apagá la tele")

    assert asker.asked == [], "no se cae en la pregunta cuando el router falla"
    assert "/ayuda" in reply


def test_someone_not_on_the_list_gets_nowhere():
    router = FakeRouter(Decision("apagar"))
    cmd, _ = build(router=router)

    reply = cmd.free_text(INTRUSO, "apagá todo")

    assert router.seen == [], "ni siquiera se interpreta el mensaje de un desconocido"
    assert "lista" in reply.lower()


def test_without_a_router_it_points_at_the_help():
    cmd, spk = build(router=None, asker=None)
    cmd.router = None

    reply = cmd.free_text(OWNER, "cómo viene el tiempo")

    assert "/ayuda" in reply
    assert spk["parlante"].said == []


def test_what_it_says_out_loud_is_the_text_from_the_message():
    """El payload de /decir llega intacto al parlante."""
    cmd, spk = build(router=FakeRouter(Decision("decir", "que ya llegué")))

    cmd.free_text(OWNER, "decí que ya llegué")

    assert spk["parlante"].said == ["que ya llegué"]


def test_every_routable_command_can_actually_run():
    """El router nombra comandos; si acá falta uno, cae en pregunta sin avisar."""
    from homeauto.route import ROUTABLE

    cmd, _ = build()
    faltan = [name for name in ROUTABLE if name not in cmd._dispatch()]

    assert faltan == [], f"el router puede pedir {faltan} y nadie los ejecuta"


def test_nothing_is_dispatched_that_the_router_cannot_ask_for():
    from homeauto.route import ROUTABLE

    cmd, _ = build()
    sobran = [name for name in cmd._dispatch() if name not in ROUTABLE]

    assert sobran == [], f"{sobran} se puede ejecutar pero el router nunca lo nombra"
