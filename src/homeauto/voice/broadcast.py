"""Anunciar algo en la casa, venga el pedido de donde venga.

Las reglas son las mismas para un comando de Telegram, una llamada HTTP o un
evento de agenda, así que viven acá una sola vez: a qué equipos, si la casa
está en descanso, y la copia escrita que siempre llega al chat.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, Iterable

log = logging.getLogger(__name__)

# Marca que los chats fuera de los de alertas reciben la misma copia.
SAME = object()


class HouseVoice:
    def __init__(
        self,
        speakers,
        default_devices: list[str],
        notify: Callable[[int, str], None],
        chat_ids: Iterable[int],
        quiet=None,
        clock: Callable[[], datetime] = datetime.now,
        alert_chat_ids: Iterable[int] = (),
    ):
        self.speakers = speakers
        self.default_devices = list(default_devices)
        self.notify = notify
        self.chat_ids = list(chat_ids)
        # Vacío: todos los chats reciben las alertas.
        self.alert_chat_ids = set(alert_chat_ids) or set(self.chat_ids)
        self.quiet = quiet
        self.clock = clock

    def resting(self) -> bool:
        return self.quiet is not None and self.quiet.is_quiet(self.clock())

    def announce(
        self,
        text: str,
        devices: list[str] | None = None,
        urgent: bool = False,
        written: str | None = None,
        actions: tuple[tuple[str, str], ...] = (),
        others=SAME,
    ) -> dict:
        """`written` es la copia del chat cuando lleva más que lo hablado.

        El aviso del monitor cita un estado HTTP y una traza: sirve leído, es
        ilegible dicho y está lleno de dígitos que Piper lee mal.
        `others` es la copia de los chats que no reciben alertas, como en `tell()`.
        """
        targets = list(devices or self.default_devices)

        # Lo urgente es lo único que pasa por encima del horario de descanso.
        if self.resting() and not urgent:
            log.info("aviso en horario de descanso: solo va al chat")
            note = "\n\n(horario de descanso: no se dijo en voz alta)"
            if others is not SAME:
                others = f"🔔 {others}{note}" if others else None
            self.tell(f"🔔 {written or text}{note}", others, actions)
            return {"spoken": False, "notified": True, "devices": targets, "problems": []}

        problems = []
        for alias in targets:
            try:
                # Solo lo urgente suena antes de hablar.
                self.speakers.get(alias).say(text, chime=urgent)
            except Exception as exc:  # noqa: BLE001 - se reporta al llamador
                log.warning("no pude hablar en %s: %s", alias, exc)
                problems.append(f"{alias}: {exc}")

        return {
            "spoken": len(problems) < len(targets),
            "notified": False,
            "devices": targets,
            "problems": problems,
        }

    def tell_everyone(self, text: str, actions: tuple[tuple[str, str], ...] = ()) -> None:
        """Lo escribe en todos los chats, con los botones de `actions` si hay."""
        self.tell(text, SAME, actions)

    def tell(self, text: str, others=SAME, actions: tuple[tuple[str, str], ...] = ()) -> None:
        """Escribe `text` en los chats de alertas y `others` en el resto.

        `others` en SAME repite `text`; vacío o None no les escribe nada.
        """
        for chat_id in self.chat_ids:
            message = text if others is SAME or chat_id in self.alert_chat_ids else others
            if not message:
                continue
            try:
                if actions:
                    self.notify(chat_id, message, actions)
                else:
                    self.notify(chat_id, message)
            except Exception:
                log.exception("no se pudo avisar al chat %s", chat_id)
