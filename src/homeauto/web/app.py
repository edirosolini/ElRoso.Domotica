"""Las rutas de la pantalla de la casa, sin nada de HTTP adentro."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, tzinfo
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from homeauto.web.apk import FILES as APPS
from homeauto.web.board import RangeError
from homeauto.web.jobs import WebError

log = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
STATIC_DIR = HERE / "static"
PAGES_DIR = HERE / "pages"

FULLCALENDAR = "fullcalendar-6.1.21"

# FullCalendar inyecta su CSS en un <style> y estila con atributos: necesita 'unsafe-inline'.
# Sus íconos (las flechas) son una fuente embebida como data: URI.
POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; font-src 'self' data:; frame-ancestors 'none'; "
    "base-uri 'none'; form-action 'none'"
)

JS = "text/javascript; charset=utf-8"
CSS = "text/css; charset=utf-8"
TEXT = "text/plain; charset=utf-8"
HTML = "text/html; charset=utf-8"
JSON = "application/json; charset=utf-8"
MANIFEST = "application/manifest+json; charset=utf-8"
PNG = "image/png"
APK = "application/vnd.android.package-archive"

# Cómo sale cada archivo de `/app/`: tipo, si es descarga y qué dice cuando falta.
APP_FILES = {
    "tele.apk": (APK, True, "Todavía no hay app de la tele en la casa."),
    "tele.json": (JSON, False, "Todavía no hay versión de la app de la tele en la casa."),
}

REVALIDATE = "no-cache"
FOREVER = "public, max-age=31536000, immutable"

# Lo único que se sirve de `static/`: nombre en la URL, tipo y cache.
STATIC = {
    "app.js": (JS, REVALIDATE),
    "kiosk.js": (JS, REVALIDATE),
    "alarm.js": (JS, REVALIDATE),
    "control.js": (JS, REVALIDATE),
    "manifest.webmanifest": (MANIFEST, REVALIDATE),
    "icon-192.png": (PNG, REVALIDATE),
    "icon-512.png": (PNG, REVALIDATE),
    "app.css": (CSS, REVALIDATE),
    f"{FULLCALENDAR}/index.global.min.js": (JS, FOREVER),
    f"{FULLCALENDAR}/es.global.min.js": (JS, FOREVER),
    f"{FULLCALENDAR}/LICENSE.md": (TEXT, FOREVER),
}

PAGES = {
    "/agenda": "agenda.html",
    "/pantalla": "pantalla.html",
    "/alarma": "alarma.html",
    "/control": "control.html",
}
FEEDS = ("/api/events", "/api/board")
RINGING = re.compile(r"/api/ringing/(\d+)")

PEOPLE = "/api/people"
JOBS = "/api/jobs"
JOB = re.compile(r"/api/jobs/(\d+)")
ITEM = re.compile(r"/api/lists/([a-z]+)/(\d+)/done")
LIST = re.compile(r"/api/lists/([a-z]+)")
PERSONS = "/api/persons"
PERSON = re.compile(r"/api/persons/(\d+)")
WRITES = ("POST", "PUT", "DELETE")
LIVE = "/api/live"
COMMAND = "/api/command"
APP = "/app"
TELE = "/api/tele"
TELE_SETUP = "/api/tele/setup"
TELE_HELLO = "/api/tele/hello"
TELE_POLL = re.compile(r"/api/tele/([^/]+)/poll")
TELE_ACK = re.compile(r"/api/tele/([^/]+)/ack")


@dataclass(frozen=True)
class Request:
    method: str
    path: str
    query: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    # La IP de quien pide.
    client: str = ""

    @classmethod
    def from_target(
        cls,
        method: str,
        target: str,
        headers: dict[str, str] | None = None,
        body: bytes = b"",
        client: str = "",
    ) -> "Request":
        """Un pedido a partir de la línea cruda; de cada parámetro vale el primero."""
        url = urlsplit(target)
        query = {key: values[0] for key, values in parse_qs(url.query).items()}
        lowered = {name.lower(): value for name, value in (headers or {}).items()}
        return cls(
            method=method, path=url.path, query=query, headers=lowered, body=body, client=client
        )


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)


def _respond(status: int, body: bytes, content_type: str, cache: str, **extra: str) -> Response:
    headers = {
        "Content-Type": content_type,
        "Cache-Control": cache,
        "Content-Security-Policy": POLICY,
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        **extra,
    }
    return Response(status=status, body=body, headers=headers)


def _json(status: int, payload, **extra: str) -> Response:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return _respond(status, raw, JSON, "no-store", **extra)


def _refuse_write(request: Request) -> Response | None:
    """Rechaza una escritura que no es JSON o que viene de otro sitio; None si pasa."""
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        return _json(415, {"error": "solo se acepta application/json"})
    # Con Origin presente, tiene que coincidir con Host.
    origin = request.headers.get("origin")
    if origin is not None:
        host = request.headers.get("host")
        if not host or urlsplit(origin).netloc != host:
            return _json(403, {"error": "escritura desde otro sitio"})
    return None


def parse_moment(text: str | None, timezone: tzinfo) -> datetime:
    """Una fecha ISO de FullCalendar, llevada a la hora local sin zona."""
    if not text:
        raise ValueError("falta la fecha")
    # Un '+' sin codificar llega como espacio.
    moment = datetime.fromisoformat(text.strip().replace(" ", "+"))
    if moment.tzinfo is None:
        return moment
    return moment.astimezone(timezone).replace(tzinfo=None)


class WebApp:
    """La agenda, el kiosco y sus datos, para el servidor de la API."""

    def __init__(
        self,
        board,
        jobs=None,
        control=None,
        static_dir: Path = STATIC_DIR,
        pages_dir: Path = PAGES_DIR,
        apps=None,
        tele=None,
    ):
        self.board = board
        self.jobs = jobs
        self.control = control
        self.apps = apps
        self.tele = tele
        self.static_dir = static_dir
        self.pages_dir = pages_dir

    def __call__(self, request: Request) -> Response:
        return self.handle(request)

    def handle(self, request: Request) -> Response:
        """La respuesta a un pedido; nunca levanta."""
        path = request.path.rstrip("/") or "/"
        if (path == PEOPLE or path == JOBS or JOB.fullmatch(path) or ITEM.fullmatch(path)
                or LIST.fullmatch(path) or path == PERSONS or PERSON.fullmatch(path)):
            return self._house(request, path)
        if path == LIVE or path == COMMAND:
            return self._control(request, path)
        if path == APP or path.startswith(APP + "/"):
            return self._app(request, path[len(APP) + 1:])
        if path == TELE or path.startswith(TELE + "/"):
            return self._tele(request, path)

        ringing = RINGING.fullmatch(path)
        known = path in PAGES or path in FEEDS or ringing or path.startswith("/static/")
        if request.method != "GET":
            if known:
                return _json(405, {"error": "método no permitido"}, Allow="GET")
            return _json(404, {"error": "no existe"})

        if path in PAGES:
            return self._page(PAGES[path])
        if path == "/api/events":
            return self._events(request.query)
        if path == "/api/board":
            return self._screen()
        if ringing:
            return self._ringing(int(ringing.group(1)))
        if request.path.startswith("/static/"):
            return self._static(request.path[len("/static/"):])
        return _json(404, {"error": "no existe"})

    def _house(self, request: Request, path: str) -> Response:
        """La gente, el padrón, los avisos y las listas: lo que la pantalla lee y escribe."""
        job = JOB.fullmatch(path)
        item = ITEM.fullmatch(path)
        items = LIST.fullmatch(path)
        person = PERSON.fullmatch(path)
        if path == PEOPLE:
            allowed = ("GET",)
        elif path == JOBS or item or items or path == PERSONS:
            allowed = ("POST",)
        elif person:
            allowed = ("PUT", "DELETE")
        else:
            allowed = ("GET", "PUT", "DELETE")
        if request.method not in allowed:
            return _json(405, {"error": "método no permitido"}, Allow=", ".join(allowed))

        if self.jobs is None:
            if path == PEOPLE:
                return _json(200, {"writable": False, "people": [], "devices": [],
                                   "persons": [], "chats": []})
            if path == PERSONS or person:
                return _json(404, {"error": "no existe"})
            if request.method in WRITES:
                return _json(405, {"error": "la pantalla no puede escribir"}, Allow="GET")
            return _json(404, {"error": "no existe"})

        payload: dict = {}
        if request.method in WRITES:
            refusal = _refuse_write(request)
            if refusal is not None:
                return refusal
            if request.method != "DELETE":
                try:
                    payload = json.loads(request.body.decode("utf-8"))
                except ValueError:
                    payload = None
                if not isinstance(payload, dict):
                    return _json(400, {"error": "se esperaba un objeto JSON"})

        try:
            if path == PEOPLE:
                return _json(200, self.jobs.people())
            if path == JOBS:
                return _json(201, self.jobs.create(payload))
            if path == PERSONS:
                return _json(201, self.jobs.add_person(payload))
            if person:
                person_id = int(person.group(1))
                if request.method == "PUT":
                    return _json(200, self.jobs.change_person(person_id, payload))
                return _json(200, self.jobs.remove_person(person_id))
            if item:
                removed = self.jobs.cross_out(item.group(1), int(item.group(2)))
                return _json(200, {"removed": removed})
            if items:
                return _json(201, self.jobs.add_items(items.group(1), payload.get("text")))
            job_id = int(job.group(1))
            if request.method == "GET":
                return _json(200, self.jobs.job(job_id))
            if request.method == "PUT":
                return _json(200, self.jobs.update(job_id, payload))
            self.jobs.delete(job_id)
            return _json(200, {"ok": True})
        except WebError as exc:
            return _json(exc.status, {"error": str(exc)})
        except Exception:  # noqa: BLE001
            log.exception("could not write from the screen")
            return _json(500, {"error": "No pude guardar el cambio."})

    def _control(self, request: Request, path: str) -> Response:
        """Lo urgente de ahora y los comandos de la pantalla de control."""
        allowed = "GET" if path == LIVE else "POST"
        if request.method != allowed:
            return _json(405, {"error": "método no permitido"}, Allow=allowed)
        if self.control is None:
            return _json(404, {"error": "no existe"})

        payload = None
        if path == LIVE:
            raw = request.query.get("chat", "")
            person = request.query.get("person")
            if person is not None:
                if "chat" in request.query or not (person.isascii() and person.isdigit()):
                    return _json(400, {"error": "falta la persona, sola"})
            elif not (raw.isascii() and raw.lstrip("-").isdigit()):
                return _json(400, {"error": "falta el chat"})
        else:
            refusal = _refuse_write(request)
            if refusal is not None:
                return refusal
            try:
                payload = json.loads(request.body.decode("utf-8"))
            except ValueError:
                payload = None
            if not isinstance(payload, dict):
                return _json(400, {"error": "se esperaba un objeto JSON"})

        try:
            if path == LIVE and person is not None:
                return _json(200, self.control.live(person_id=int(person)))
            if path == LIVE:
                return _json(200, self.control.live(int(raw)))
            return _json(200, self.control.run(payload))
        except WebError as exc:
            return _json(exc.status, {"error": str(exc)})
        except Exception:  # noqa: BLE001
            log.exception("la pantalla de control se rompió")
            return _json(500, {"error": "No pude atender el pedido."})

    def _tele(self, request: Request, path: str) -> Response:
        """El registro, la consulta y las confirmaciones de la app de la tele."""
        poll = TELE_POLL.fullmatch(path)
        ack = TELE_ACK.fullmatch(path)
        if path == TELE_SETUP or poll:
            allowed = "GET"
        elif path == TELE_HELLO or ack:
            allowed = "POST"
        else:
            return _json(404, {"error": "no existe"})
        if request.method != allowed:
            return _json(405, {"error": "método no permitido"}, Allow=allowed)
        if self.tele is None:
            return _json(404, {"error": "no existe"})

        payload = None
        if allowed == "POST":
            refusal = _refuse_write(request)
            if refusal is not None:
                return refusal
            try:
                payload = json.loads(request.body.decode("utf-8"))
            except ValueError:
                payload = None
            if not isinstance(payload, dict):
                return _json(400, {"error": "se esperaba un objeto JSON"})

        try:
            if path == TELE_SETUP:
                return _json(200, self.tele.setup())
            if path == TELE_HELLO:
                return _json(200, self.tele.hello(payload, address=request.client))
            if ack:
                return _json(200, self.tele.ack(ack.group(1), payload))
            return _json(200, self.tele.poll(poll.group(1), address=request.client))
        except WebError as exc:
            return _json(exc.status, {"error": str(exc)})
        except Exception:  # noqa: BLE001
            log.exception("la app de la tele se rompió")
            return _json(500, {"error": "No pude atender a la tele."})

    def _app(self, request: Request, name: str) -> Response:
        """Devuelve el archivo `name` de la app; 404 si no se ofrece o no está."""
        if name not in APPS or name not in APP_FILES:
            return _json(404, {"error": "no existe"})
        if request.method != "GET":
            return _json(405, {"error": "método no permitido"}, Allow="GET")
        if self.apps is None:
            return _json(404, {"error": "no existe"})
        try:
            data = self.apps.get(name)
        except OSError:
            log.exception("no pude leer la app %s", name)
            return _json(500, {"error": "No pude leer la app."})
        content_type, download, missing = APP_FILES[name]
        if data is None:
            return _json(404, {"error": missing})
        extra = {"Content-Disposition": f'attachment; filename="{name}"'} if download else {}
        return _respond(200, data, content_type, "no-store", **extra)

    def _page(self, name: str) -> Response:
        return _respond(200, (self.pages_dir / name).read_bytes(), HTML, REVALIDATE)

    def _static(self, name: str) -> Response:
        entry = STATIC.get(name)
        if entry is None:
            return _json(404, {"error": "no existe"})
        content_type, cache = entry
        return _respond(200, (self.static_dir / name).read_bytes(), content_type, cache)

    def _events(self, query: dict[str, str]) -> Response:
        timezone = getattr(self.board, "timezone", None)
        try:
            start = parse_moment(query.get("start"), timezone)
            end = parse_moment(query.get("end"), timezone)
        except (TypeError, ValueError):
            return _json(400, {"error": "rango inválido: hacen falta start y end en ISO"})
        try:
            return _json(200, self.board.events(start, end))
        except RangeError as exc:
            return _json(400, {"error": f"rango inválido: {exc}"})
        except Exception:  # noqa: BLE001
            log.exception("could not build the events feed")
            return _json(500, {"error": "No pude armar la agenda."})

    def _ringing(self, job_id: int) -> Response:
        try:
            return _json(200, self.board.ringing(job_id))
        except Exception:  # noqa: BLE001
            log.exception("could not read the ringing alarm %s", job_id)
            return _json(500, {"error": "No pude leer la alarma."})

    def _screen(self) -> Response:
        try:
            return _json(200, self.board.screen())
        except Exception:  # noqa: BLE001
            log.exception("could not build the screen")
            return _json(500, {"error": "No pude armar la pantalla."})
