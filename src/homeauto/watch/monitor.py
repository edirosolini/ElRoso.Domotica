"""Vigilancia de servicios externos, sin volverse ruido.

Solo habla cuando algo *cambia*, y aguanta dos fallos seguidos antes de
declarar una caída.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Callable

from homeauto.polish import as_is
from homeauto.watch.checks import Check, HttpProbe, ProbeSkipped, TcpProbe, run_check
from homeauto.watch.status import Status, StatusStore

log = logging.getLogger(__name__)

FAILURES_TO_DECLARE = 2
# Los primeros re-avisos, contados desde el aviso de caída; después, uno cada `REMIND_EVERY`.
REMIND_DELAYS = (timedelta(minutes=5), timedelta(minutes=10), timedelta(minutes=15))
REMIND_EVERY = timedelta(minutes=30)


def down_line(monitor, polish: Callable[..., str] = as_is) -> str:
    """Los servicios caídos en una oración, o nada si están todos en pie.

    El silencio es la buena noticia: el estado completo está en `/estado`.
    """
    down = sorted(name for name, state in monitor.snapshot().items() if not state.up)
    if not down:
        return ""
    wording = {check.name: check.down for check in getattr(monitor, "checks", ())}
    plain = [name for name in down if wording.get(name, Check.down) == Check.down]
    clauses = [f"{name} {wording[name]}" for name in down if name not in plain]
    if len(plain) == 1:
        clauses.insert(0, f"{plain[0]} {Check.down}")
    elif plain:
        clauses.insert(0, f"no responden {', '.join(plain[:-1])} ni {plain[-1]}")
    text = clauses[0] if len(clauses) == 1 else f"{', '.join(clauses[:-1])}, y {clauses[-1]}"
    return polish(f"Ojo: {text}.", must_keep=tuple(down))


class Monitor:
    def __init__(
        self,
        checks: list[Check],
        store: StatusStore,
        announce: Callable[[str, bool], None],
        run: Callable = run_check,
        http: HttpProbe | None = None,
        tcp: TcpProbe | None = None,
        clock: Callable[[], datetime] = datetime.now,
        failures_to_declare: int = FAILURES_TO_DECLARE,
        polish: Callable[..., str] = as_is,
        remind: Callable[..., None] | None = None,
        tell_others: Callable[[int, str], None] | None = None,
        online: Callable[[], bool] = lambda: True,
    ):
        self.checks = checks
        self.online = online
        self.store = store
        self.announce = announce
        self.remind = remind
        self.tell_others = tell_others
        self.run = run
        self.http = http or HttpProbe()
        self.tcp = tcp or TcpProbe()
        self.clock = clock
        self.failures_to_declare = failures_to_declare
        self.polish = polish

    def snapshot(self) -> dict[str, Status]:
        """El estado de lo que se vigila *ahora*.

        Filtrado por los chequeos configurados, no por la tabla entera: un
        chequeo renombrado deja una fila que nadie va a volver a chequear.
        """
        watched = {check.name for check in self.checks}
        return {name: state for name, state in self.store.all().items() if name in watched}

    def run_once(self) -> list[str]:
        # Sin internet en la ronda no se chequea ni se cuenta nada.
        if not self.online():
            log.info("no uplink: skipping the service checks")
            return []
        now = self.clock()
        announced = []

        for check in self.checks:
            previous = self.store.get(check.name)
            # Una sonda con memoria arranca sabiendo lo último guardado.
            restore = getattr(check.probe, "restore", None)
            if restore is not None:
                restore(previous)
            try:
                result = self.run(check, http=self.http, tcp=self.tcp)
            except ProbeSkipped as exc:
                log.info("skipping %s this round: %s", check.name, exc)
                continue
            except Exception:  # noqa: BLE001 - el loop no puede morirse por un chequeo
                log.exception("falló el chequeo de %s", check.name)
                continue

            message = self._advance(check, result, previous, now)
            if message:
                announced.append(message)

        return announced

    def _say(self, text: str, name: str) -> str:
        """La mitad hablada, pulida. El detalle de la sonda no llega acá: lleva
        un estado HTTP y una duración, y un dígito se lee mal."""
        return self.polish(text, must_keep=(name,))

    def _advance(self, check: Check, result, previous: Status | None, now: datetime) -> str | None:
        was_alerted = previous.alerted if previous else False
        failures = previous.failures if previous else 0

        if result.up:
            # Solo vale contarlo si alguien se enteró de la caída.
            message = None
            if was_alerted:
                message = self._say(f"{check.name} {check.up}.", check.name)
                self.announce(message, False, result.detail)
            self.store.save(Status(check.name, True, 0, False, result.detail, now))
            self.store.clear_alert(check.name)
            return message

        failures += 1
        if not was_alerted and failures >= self.failures_to_declare:
            # Se guarda antes de avisar: el botón de confirmar llega con el aviso.
            self.store.clear_alert(check.name)
            self.store.save(Status(check.name, False, failures, True, result.detail, now))
            self.store.plan_reminder(check.name, 0, now + REMIND_DELAYS[0])
            message = self._say(f"Atención: {check.name} {check.down}.", check.name)
            self.announce(message, result.urgent, result.detail, check=check.name)
            return message

        self.store.save(Status(check.name, False, failures, was_alerted, result.detail, now))
        if was_alerted and check.remind and self._reminder_due(previous, now):
            return self._remind(check, previous.reminders + 1, result.detail, now)
        return None

    def _reminder_due(self, state: Status, now: datetime) -> bool:
        """Si toca re-avisar una caída que nadie confirmó."""
        return (
            self.remind is not None
            and not state.acked_by
            and state.next_reminder is not None
            and now >= state.next_reminder
        )

    def _remind(self, check: Check, count: int, detail: str, now: datetime) -> str:
        """Re-avisa la caída y agenda el re-aviso siguiente."""
        self.store.plan_reminder(check.name, count, now + _gap(count))
        message = self._say(f"Atención: {check.name} {check.still}.", check.name)
        self.remind(message, check.name, detail)
        return message

    def acknowledge(self, name: str, who: str, chat_id: int) -> str:
        """Confirma la caída de `name` a nombre de `who` y avisa a los otros chats de alertas."""
        check = next((check for check in self.checks if check.name == name), None)
        if check is None:
            return f"No vigilo nada llamado {name}."
        if self.store.acknowledge(name, who, self.clock()):
            if self.tell_others is not None:
                self.tell_others(chat_id, f"✅ {who} confirmó: {name} {check.down}")
            return f"✅ Confirmado: {name} {check.down}. No vuelvo a avisar hasta que vuelva."
        state = self.store.get(name)
        if state is None or state.up or not state.alerted:
            return f"{name} ya {check.up}."
        return f"La caída de {name} ya estaba confirmada por {state.acked_by}."


def _gap(count: int) -> timedelta:
    """Lo que falta del re-aviso número `count` al siguiente."""
    if count < len(REMIND_DELAYS):
        return REMIND_DELAYS[count] - REMIND_DELAYS[count - 1]
    return REMIND_EVERY
