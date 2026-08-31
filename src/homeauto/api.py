"""A door for other systems to speak through the house.

Long polling means the bot itself needs no inbound port. This does: a small
HTTP endpoint on the LAN so a backup script, a monitor or a cron can announce
something. It is protected by a shared token and never exposed to internet.
"""

from __future__ import annotations

import hmac
import json
import logging
import threading
from datetime import datetime
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Iterable

from homeauto.polish import as_is
from homeauto.voice.broadcast import HouseVoice

log = logging.getLogger(__name__)

MAX_BODY = 8 * 1024
MAX_TEXT = 500


class ApiError(Exception):
    """The request was understood but cannot be served."""


class Unauthorized(Exception):
    """Wrong or missing token."""


class ApiService:
    """The logic behind the endpoint, free of HTTP."""

    def __init__(
        self,
        token: str,
        speakers,
        default_devices: list[str],
        notify: Callable[[int, str], None],
        chat_ids: Iterable[int],
        quiet=None,
        clock: Callable[[], datetime] = datetime.now,
        polish: Callable[..., str] = as_is,
    ):
        self.token = token
        self.speakers = speakers
        self.polish = polish
        self.voice = HouseVoice(
            speakers=speakers,
            default_devices=default_devices,
            notify=notify,
            chat_ids=chat_ids,
            quiet=quiet,
            clock=clock,
        )

    def _authenticate(self, token: str) -> None:
        # compare_digest so a wrong token cannot be guessed one character at a time.
        if not token or not self.token or not hmac.compare_digest(token, self.token):
            raise Unauthorized("token inválido")

    def _targets(self, payload: dict) -> list[str]:
        asked = payload.get("devices") or self.voice.default_devices
        if isinstance(asked, str):
            asked = [asked]

        unknown = [alias for alias in asked if not self.speakers.has(alias)]
        if unknown:
            raise ApiError(f"equipos desconocidos: {', '.join(unknown)}")
        return list(dict.fromkeys(alias.strip().lower() for alias in asked))

    def health(self) -> dict:
        return {"ok": True, "devices": list(self.speakers.aliases)}

    def say(self, token: str, payload: dict) -> dict:
        self._authenticate(token)

        text = str(payload.get("text") or "").strip()
        if not text:
            raise ApiError("falta 'text'")
        if len(text) > MAX_TEXT:
            raise ApiError(f"'text' es demasiado largo (máximo {MAX_TEXT})")

        result = self.voice.announce(
            self.polish(text),
            devices=self._targets(payload),
            urgent=bool(payload.get("urgent")),
        )
        if not result["spoken"] and not result["notified"]:
            raise ApiError("; ".join(result["problems"]))
        return result


class _Handler(BaseHTTPRequestHandler):
    server_version = "domotica"

    def __init__(self, *args, service: ApiService, **kwargs):
        self.service = service
        super().__init__(*args, **kwargs)

    def log_message(self, *args):
        pass

    def _reply(self, status: int, body: dict) -> None:
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):  # noqa: N802 - nombre impuesto por http.server
        if self.path.rstrip("/") == "/health":
            self._reply(200, self.service.health())
        else:
            self._reply(404, {"error": "no existe"})

    def do_POST(self):  # noqa: N802
        if self.path.rstrip("/") != "/say":
            self._reply(404, {"error": "no existe"})
            return

        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            self._reply(413, {"error": "cuerpo demasiado grande"})
            return

        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw or b"{}")
            if not isinstance(payload, dict):
                raise ValueError("se esperaba un objeto")
        except ValueError as exc:
            self._reply(400, {"error": f"JSON inválido: {exc}"})
            return

        token = self.headers.get("X-Token", "") or str(payload.get("token", ""))
        try:
            self._reply(200, self.service.say(token, payload))
        except Unauthorized as exc:
            self._reply(401, {"error": str(exc)})
        except ApiError as exc:
            self._reply(400, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            log.exception("error inesperado en la API")
            self._reply(500, {"error": str(exc)})


class ApiServer:
    def __init__(self, service: ApiService, port: int, host: str = "0.0.0.0"):
        self.service = service
        self.port = port
        self.host = host
        self._server: ThreadingHTTPServer | None = None

    def start(self) -> None:
        handler = partial(_Handler, service=self.service)
        self._server = ThreadingHTTPServer((self.host, self.port), handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        log.info("API escuchando en %s:%s", self.host, self.actual_port)

    @property
    def actual_port(self) -> int:
        return self._server.server_address[1] if self._server else self.port

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
