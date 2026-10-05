"""Servidor HTTP de la LAN para que otros sistemas usen la casa.

`POST /say` anuncia un texto y pide token compartido; `GET /health` no lo pide.
El resto de las rutas son de la pantalla de la casa (`web.WebApp`), abiertas a la LAN.
"""

from __future__ import annotations

import hmac
import json
import logging
import threading
from datetime import datetime
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Iterable, Protocol

from homeauto.polish import as_is
from homeauto.voice.broadcast import HouseVoice
from homeauto.web.app import Request, Response

log = logging.getLogger(__name__)

MAX_BODY = 8 * 1024
MAX_TEXT = 500


class ApiError(Exception):
    """El pedido se entendió pero no se puede atender."""


class Unauthorized(Exception):
    """Token equivocado o ausente."""


class Web(Protocol):
    def handle(self, request: Request) -> Response: ...


class ApiService:
    """La lógica del endpoint, sin nada de HTTP."""

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
        # compare_digest para que un token equivocado no se adivine de a un carácter.
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

    def __init__(self, *args, service: ApiService, web: Web | None = None, **kwargs):
        self.service = service
        self.web = web
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

    def _delegate(self, method: str) -> None:
        """Pasa el pedido a la pantalla de la casa, o 404 si no está."""
        if self.web is None:
            self._reply(404, {"error": "no existe"})
            return
        body = b""
        if method != "GET":
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                self._reply(413, {"error": "cuerpo demasiado grande"})
                return
            body = self.rfile.read(length) if length else b""
        response = self.web.handle(
            Request.from_target(method, self.path, headers=dict(self.headers.items()), body=body)
        )
        self.send_response(response.status)
        for name, value in response.headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(response.body)))
        self.end_headers()
        self.wfile.write(response.body)

    def do_GET(self):  # noqa: N802 - nombre impuesto por http.server
        if self.path.split("?", 1)[0].rstrip("/") == "/health":
            self._reply(200, self.service.health())
        else:
            self._delegate("GET")

    def do_PUT(self):  # noqa: N802
        self._delegate("PUT")

    def do_DELETE(self):  # noqa: N802
        self._delegate("DELETE")

    def do_POST(self):  # noqa: N802
        if self.path.split("?", 1)[0].rstrip("/") != "/say":
            self._delegate("POST")
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
    def __init__(
        self, service: ApiService, port: int, host: str = "0.0.0.0", web: Web | None = None
    ):
        self.service = service
        self.web = web
        self.port = port
        self.host = host
        self._server: ThreadingHTTPServer | None = None

    def start(self) -> None:
        handler = partial(_Handler, service=self.service, web=self.web)
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
