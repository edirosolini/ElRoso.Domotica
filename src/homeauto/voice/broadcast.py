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


class HouseVoice:
    def __init__(
        self,
        speakers,
        default_devices: list[str],
        notify: Callable[[int, str], None],
        chat_ids: Iterable[int],
        quiet=None,
        clock: Callable[[], datetime] = datetime.now,
    ):
        self.speakers = speakers
        self.default_devices = list(default_devices)
        self.notify = notify
        self.chat_ids = list(chat_ids)
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
    ) -> dict:
        """`written` es la copia del chat cuando lleva más que lo hablado.

        El aviso del monitor cita un estado HTTP y una traza: sirve leído, es
        ilegible dicho y está lleno de dígitos que Piper lee mal.
        """
        targets = list(devices or self.default_devices)

        # Lo urgente es lo único que pasa por encima del horario de descanso.
        if self.resting() and not urgent:
            log.info("aviso en horario de descanso: solo va al chat")
            self.tell_everyone(
                f"🔔 {written or text}\n\n(horario de descanso: no se dijo en voz alta)",
                actions,
            )
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
        for chat_id in self.chat_ids:
            try:
                if actions:
                    self.notify(chat_id, text, actions)
                else:
                    self.notify(chat_id, text)
            except Exception:
                log.exception("no se pudo avisar al chat %s", chat_id)
