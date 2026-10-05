"""Las rutas de la pantalla, sin servidor HTTP de por medio."""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from homeauto.web.app import FULLCALENDAR, STATIC_DIR, Request, WebApp
from homeauto.web.board import RangeError

TZ = ZoneInfo("America/Argentina/Buenos_Aires")


class StubBoard:
    """Anota los rangos pedidos y contesta como el tablero de verdad."""

    def __init__(self, fail=None):
        self.asked = []
        self.fail = fail
        self.timezone = TZ

    def events(self, start, end):
        self.asked.append((start, end))
        if self.fail:
            raise self.fail
        if end <= start:
            raise RangeError("invertido")
        return {"events": [{"title": "<img src=x onerror=alert(1)>", "start": "2026-10-06T08:00:00"}],
                "calendars": [], "problems": []}

    def screen(self):
        if self.fail:
            raise self.fail
        return {"now": "2026-10-05T12:00:00-03:00", "quiet": True, "weather": None,
                "lists": {"compras": ["leche"]}, "problems": []}


@pytest.fixture
def board():
    return StubBoard()


@pytest.fixture
def app(board):
    return WebApp(board)


def get(app, path, **query):
    return app.handle(Request(method="GET", path=path, query=query))


def body_json(response):
    return json.loads(response.body.decode("utf-8"))


# --- las páginas ---


@pytest.mark.parametrize("path", ["/agenda", "/agenda/", "/pantalla"])
def test_the_pages_answer_html_without_a_login(app, path):
    response = get(app, path)

    assert response.status == 200
    assert response.headers["Content-Type"].startswith("text/html")
    assert response.body.startswith(b"<!doctype html>")


def test_the_agenda_loads_the_vendored_calendar_and_no_cdn(app):
    page = get(app, "/agenda").body.decode("utf-8")

    assert f'src="/static/{FULLCALENDAR}/index.global.min.js"' in page
    assert f'src="/static/{FULLCALENDAR}/es.global.min.js"' in page
    assert 'src="/static/app.js"' in page
    assert "cdn" not in page.lower()
    assert "http://" not in page and "https://" not in page


def test_the_kiosk_loads_its_own_script(app):
    page = get(app, "/pantalla").body.decode("utf-8")

    assert 'src="/static/kiosk.js"' in page
    assert "fullcalendar" not in page


def test_the_kiosk_has_a_place_for_today(app):
    page = get(app, "/pantalla").body.decode("utf-8")
    script = get(app, "/static/kiosk.js").body.decode("utf-8")

    assert 'id="today"' in page
    assert "data.today" in script
    assert "innerHTML" not in script


@pytest.mark.parametrize("path", ["/agenda", "/pantalla"])
def test_the_pages_have_no_inline_javascript(app, path):
    page = get(app, path).body.decode("utf-8").lower()

    assert page.count("<script") == page.count("<script src=")
    assert "onload=" not in page and "onclick=" not in page
    assert "javascript:" not in page


def test_every_answer_carries_the_security_headers(app):
    for response in (get(app, "/agenda"), get(app, "/api/board"), get(app, "/nada")):
        policy = response.headers["Content-Security-Policy"]
        assert "default-src 'self'" in policy
        assert "script-src 'self'" in policy
        assert "frame-ancestors 'none'" in policy
        assert "unsafe-eval" not in policy
        assert "'unsafe-inline'" not in policy.split("script-src")[1].split(";")[0]
        assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_the_policy_lets_fullcalendar_load_its_icon_font(app):
    """Las flechas de FullCalendar son una fuente embebida como data: URI."""
    bundle = (STATIC_DIR / FULLCALENDAR / "index.global.min.js").read_text(encoding="utf-8")
    assert 'src:url("data:application/x-font-ttf' in bundle

    policy = get(app, "/agenda").headers["Content-Security-Policy"]
    fonts = policy.split("font-src")[1].split(";")[0]
    assert "data:" in fonts


# --- /api/events ---


def test_the_events_feed_reads_the_range_fullcalendar_sends(app, board):
    response = get(
        app, "/api/events", start="2026-09-28T00:00:00-03:00", end="2026-11-09T00:00:00-03:00"
    )

    assert response.status == 200
    assert response.headers["Content-Type"].startswith("application/json")
    assert response.headers["Cache-Control"] == "no-store"
    assert board.asked == [(datetime(2026, 9, 28), datetime(2026, 11, 9))]
    assert body_json(response)["events"][0]["start"] == "2026-10-06T08:00:00"


def test_an_offset_is_brought_to_the_house_hour(app, board):
    get(app, "/api/events", start="2026-10-05T03:00:00Z", end="2026-10-06T03:00:00Z")

    assert board.asked == [(datetime(2026, 10, 5), datetime(2026, 10, 6))]


def test_a_plus_sign_that_became_a_space_is_still_read(app, board):
    get(app, "/api/events", start="2026-10-05T03:00:00 00:00", end="2026-10-06")

    assert board.asked == [(datetime(2026, 10, 5), datetime(2026, 10, 6))]


def test_plain_dates_are_read_as_local_midnight(app, board):
    get(app, "/api/events", start="2026-10-05", end="2026-10-12")

    assert board.asked == [(datetime(2026, 10, 5), datetime(2026, 10, 12))]


def test_titles_travel_as_data_not_markup(app):
    raw = get(app, "/api/events", start="2026-10-05", end="2026-10-12").body.decode("utf-8")

    assert json.loads(raw)["events"][0]["title"] == "<img src=x onerror=alert(1)>"


@pytest.mark.parametrize(
    "query",
    [
        {},
        {"start": "2026-10-05"},
        {"end": "2026-10-05"},
        {"start": "ayer", "end": "2026-10-05"},
        {"start": "2026-10-12", "end": "2026-10-05"},
    ],
)
def test_a_bad_range_gets_400(app, query):
    response = get(app, "/api/events", **query)

    assert response.status == 400
    assert "error" in body_json(response)


def test_a_range_the_board_refuses_gets_400():
    app = WebApp(StubBoard(fail=RangeError("el rango no puede pasar de sesenta y dos días")))

    response = get(app, "/api/events", start="2026-10-01", end="2027-01-01")

    assert response.status == 400
    assert "sesenta y dos" in body_json(response)["error"]


def test_a_board_that_breaks_gets_500_without_the_details():
    app = WebApp(StubBoard(fail=RuntimeError("https://calendar.google.com/privada")))

    for response in (
        get(app, "/api/events", start="2026-10-05", end="2026-10-12"),
        get(app, "/api/board"),
    ):
        assert response.status == 500
        assert b"calendar.google.com" not in response.body


# --- /api/board ---


def test_the_board_feed_is_the_screen(app):
    response = get(app, "/api/board")

    assert response.status == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert body_json(response)["quiet"] is True
    assert body_json(response)["lists"] == {"compras": ["leche"]}


# --- /static ---


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("app.js", "text/javascript"),
        ("kiosk.js", "text/javascript"),
        ("app.css", "text/css"),
        (f"{FULLCALENDAR}/index.global.min.js", "text/javascript"),
        (f"{FULLCALENDAR}/es.global.min.js", "text/javascript"),
        (f"{FULLCALENDAR}/LICENSE.md", "text/plain"),
    ],
)
def test_the_static_files_are_served(app, name, kind):
    response = get(app, f"/static/{name}")

    assert response.status == 200
    assert response.headers["Content-Type"].startswith(kind)
    assert response.body
    assert "Cache-Control" in response.headers


def test_the_vendored_bundle_is_cached_for_long_and_ours_revalidate(app):
    vendored = get(app, f"/static/{FULLCALENDAR}/index.global.min.js")
    ours = get(app, "/static/app.js")

    assert "immutable" in vendored.headers["Cache-Control"]
    assert ours.headers["Cache-Control"] == "no-cache"


def test_the_bundle_is_the_pinned_version_with_its_license(app):
    bundle = get(app, f"/static/{FULLCALENDAR}/index.global.min.js").body
    license_text = get(app, f"/static/{FULLCALENDAR}/LICENSE.md").body

    assert FULLCALENDAR == "fullcalendar-6.1.21"
    assert b"FullCalendar Standard Bundle v6.1.21" in bundle[:200]
    assert b"MIT License" in license_text


@pytest.mark.parametrize(
    "name",
    [
        "../app.py",
        "..%2Fapp.py",
        "../../config.py",
        "/etc/passwd",
        "board.py",
        "",
        f"{FULLCALENDAR}/../../app.py",
        "app.js/",
    ],
)
def test_only_the_listed_files_are_served(app, name):
    assert get(app, f"/static/{name}").status == 404


# --- lo demás ---


def test_an_unknown_path_gets_404(app):
    assert get(app, "/otra-cosa").status == 404


def test_writing_is_not_allowed_yet(app):
    response = app.handle(Request(method="POST", path="/api/events", query={}))

    assert response.status == 405
    assert response.headers["Allow"] == "GET"


def test_a_post_to_an_unknown_path_gets_404(app):
    assert app.handle(Request(method="POST", path="/otra-cosa", query={})).status == 404


def test_a_request_is_built_from_the_raw_target():
    request = Request.from_target("GET", "/api/events?start=2026-10-05&end=2026-10-12&start=x")

    assert request.path == "/api/events"
    assert request.query == {"start": "2026-10-05", "end": "2026-10-12"}
