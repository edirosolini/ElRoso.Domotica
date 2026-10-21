"""El registro de la app de la tele y su consulta periódica, sin nada de HTTP."""

from __future__ import annotations

from typing import Iterable

from homeauto.people import display_name
from homeauto.tele import ACK_STATES, CAPS, TeleLink, normalize
from homeauto.web.jobs import NotFound, WebError

MAX_VERSION = 40


class TeleService:
    """Lo que la app de la tele pide: con qué armarse, registrarse y qué mostrar ahora."""

    def __init__(
        self,
        link: TeleLink,
        devices: Iterable[str],
        people,
        chat_ids: Iterable[int],
        screens,
    ):
        self.link = link
        self.devices = tuple(normalize(alias) for alias in devices)
        self.people = people
        self.chat_ids = sorted(chat_ids)
        # El `ScreenStore` que dice qué alarma suena en cada tele.
        self.screens = screens

    def setup(self) -> dict:
        """Las teles con pantalla y la gente de la casa, para configurar la app."""
        names = self.people.names()
        return {
            "devices": list(self.devices),
            "people": [
                {"chat_id": chat_id, "name": display_name(chat_id, names)}
                for chat_id in self.chat_ids
            ],
        }

    def hello(self, body: dict, address: str = "") -> dict:
        """Registra la tele tras validar el pedido; devuelve el alias y lo que se le aceptó."""
        alias = body.get("alias")
        if not isinstance(alias, str) or normalize(alias) not in self.devices:
            raise WebError("Esa tele no tiene pantalla en la casa.")
        version_name = body.get("version_name")
        if not isinstance(version_name, str) or len(version_name) > MAX_VERSION:
            raise WebError(f"La versión tiene que ser un texto de hasta {MAX_VERSION} caracteres.")
        version_code = body.get("version_code")
        if type(version_code) is not int or version_code < 0:
            raise WebError("El código de versión tiene que ser un entero desde cero.")
        caps = body.get("caps")
        if not isinstance(caps, list):
            raise WebError("Las capacidades tienen que ser una lista.")
        known = list(dict.fromkeys(cap for cap in caps if cap in CAPS))
        tele = self.link.hello(alias, version_name, version_code, known, address)
        return {"alias": tele.alias, "caps": list(tele.caps)}

    def poll(self, alias: str, address: str = "") -> dict:
        """Cuenta como latido y devuelve la alarma que suena en esa tele y sus órdenes pendientes."""
        alias = normalize(alias)
        if alias not in self.devices or not self.link.beat(alias, address):
            raise NotFound("Esa tele no está registrada.")
        return {"alarm": self.screens.job_for(alias), "orders": self.link.orders(alias)}

    def ack(self, alias: str, body: dict) -> dict:
        """Anota lo que la app dice de una orden; `accepted` es falso si ya no estaba abierta."""
        alias = normalize(alias)
        if alias not in self.devices:
            raise NotFound("Esa tele no está registrada.")
        seq = body.get("seq")
        if type(seq) is not int or seq < 0:
            raise WebError("El seq tiene que ser un entero desde cero.")
        state = body.get("state")
        if state not in ACK_STATES:
            raise WebError(f"El estado tiene que ser uno de: {', '.join(ACK_STATES)}.")
        accepted = self.link.ack(alias, seq, state)
        if accepted is None:
            raise NotFound("Esa tele no está registrada.")
        return {"accepted": accepted}
