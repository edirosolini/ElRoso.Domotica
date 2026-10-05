"""Las rutas de la pantalla, sin servidor HTTP de por medio."""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from homeauto.web.app import FULLCALENDAR, STATIC_DIR, Request, WebApp
from homeauto.web.board import RangeError
from homeauto.web.jobs import NotFound, ReadOnly, WebError

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


def test_the_kiosk_shows_what_comes_next_and_the_sky_icon(app):
    page = get(app, "/pantalla").body.decode("utf-8")
    script = get(app, "/static/kiosk.js").body.decode("utf-8")

    for place in ("next-title", "next-meta", "weather-icon", "chip-max", "chip-min", "chip-rain",
                  "count-today", "count-compras", "count-pendientes"):
        assert f'id="{place}"' in page, place
    assert "data.next" in script
    assert "weather.icon" in script
    assert "Nada más por hoy" in script


def test_the_kiosk_goes_to_night_tokens_in_the_quiet_hours(app):
    script = get(app, "/static/kiosk.js").body.decode("utf-8")
    css = get(app, "/static/app.css").body.decode()

    assert 'setAttribute("data-theme", "night")' in script
    assert ':root[data-theme="night"]' in css


def test_the_agenda_has_a_form_to_write_and_the_script_uses_it(app):
    page = get(app, "/agenda").body.decode("utf-8")
    script = get(app, "/static/app.js").body.decode("utf-8")

    for field in ("editor-type", "editor-message", "editor-when", "editor-repeat",
                  "editor-device", "editor-author", "detail-edit", "detail-delete", "new-job"):
        assert f'id="{field}"' in page, field
    assert 'maxlength="500"' in page
    assert "/api/jobs" in script and "/api/people" in script
    assert '"Content-Type": "application/json"' in script
    assert "innerHTML" not in script


def test_the_agenda_has_its_own_bar_and_four_views(app):
    page = get(app, "/agenda").body.decode("utf-8")
    script = get(app, "/static/app.js").body.decode("utf-8")

    for place in ("title", "prev", "next", "today", "views", "toast"):
        assert f'id="{place}"' in page, place
    for view in ("dayGridMonth", "timeGridWeek", "timeGridDay", "listWeek"):
        assert f'data-view="{view}"' in page, view
    assert "headerToolbar: false" in script
    assert "eventDidMount" in script and '"--ev"' in script
    assert 'display = "block"' in script


def test_the_agenda_tells_with_a_toast_not_an_alert(app):
    script = get(app, "/static/app.js").body.decode("utf-8")

    assert "alert(" not in script
    assert "toast(" in script


def test_the_form_picks_type_and_days_with_buttons(app):
    page = get(app, "/agenda").body.decode("utf-8")

    for kind in ("alarm", "reminder", "timer"):
        assert f'data-type="{kind}"' in page, kind
    for day in range(1, 8):
        assert f'data-day="{day}"' in page, day


def test_the_month_shows_five_per_day_and_folds_what_already_passed_today(app):
    script = get(app, "/static/app.js").body.decode("utf-8")

    assert "dayMaxEvents: 5" in script
    assert "isPastToday" in script


def test_the_agenda_refetches_its_events_every_minute(app):
    script = get(app, "/static/app.js").body.decode("utf-8")

    assert "TICK_MS = 60000" in script
    refresh = script.split("function refresh()")[1].split("\n  }\n")[0]
    assert "refetchEvents()" in refresh
    assert "setInterval(refresh, TICK_MS)" in script


def test_on_a_wide_screen_the_calendar_fits_the_window_without_page_scroll(app):
    script = get(app, "/static/app.js").body.decode("utf-8")
    css = get(app, "/static/app.css").body.decode("utf-8")

    assert "fitHeight" in script
    assert 'setOption("height"' in script
    assert 'setOption("dayMaxEvents", true)' in script
    assert '"resize"' in script
    wide = css.split("@media (min-width: 720px)")[1]
    assert "min-height: 0" in wide


def test_week_and_day_open_scrolled_to_the_current_hour(app):
    script = get(app, "/static/app.js").body.decode("utf-8")

    assert "scrollTime: nowScroll(new Date())" in script
    assert 'setOption("scrollTime", nowScroll(new Date()))' in script
    assert 'setProp("display"' in script
    assert "dayCellDidMount" in script


def test_the_kiosk_adds_items_to_both_lists(app):
    page = get(app, "/pantalla").body.decode("utf-8")
    script = get(app, "/static/kiosk.js").body.decode("utf-8")

    for name in ("compras", "pendientes"):
        assert f'id="add-{name}"' in page, name
        assert f'id="add-{name}-text"' in page, name
    assert '"/api/lists/" + encodeURIComponent(name), {' in script
    assert '"submit"' in script


def test_the_kiosk_crosses_items_out(app):
    script = get(app, "/static/kiosk.js").body.decode("utf-8")

    assert "/api/lists/" in script and "/done" in script
    assert '"Content-Type": "application/json"' in script
    assert "innerHTML" not in script


@pytest.mark.parametrize("name", ["app.js", "kiosk.js"])
def test_our_scripts_stay_in_old_javascript(app, name):
    script = get(app, f"/static/{name}").body.decode("utf-8")

    for modern in ("=>", "let ", "const ", "`", "async ", "?.", "??", "replaceChildren"):
        assert modern not in script, modern
    assert "innerHTML" not in script


@pytest.mark.parametrize("name", ["app.js", "kiosk.js"])
def test_our_scripts_style_only_through_set_property(app, name):
    script = get(app, f"/static/{name}").body.decode("utf-8")

    assert script.count(".style.") == script.count(".style.setProperty(")


@pytest.mark.parametrize("path", ["/agenda", "/pantalla"])
def test_the_pages_have_no_inline_styles(app, path):
    page = get(app, path).body.decode("utf-8").lower()

    assert "style=" not in page and "<style" not in page


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


@pytest.mark.parametrize("path", ["/agenda", "/pantalla"])
def test_the_pages_declare_both_color_schemes(app, path):
    page = get(app, path).body.decode()

    assert '<meta name="color-scheme" content="light dark">' in page


def test_the_style_follows_the_device_theme_also_inside_fullcalendar(app):
    css = get(app, "/static/app.css").body.decode()
    dark = css.split("@media (prefers-color-scheme: dark)")[1]

    assert "--bg:" in dark and "--text:" in dark and "--card:" in dark
    assert "--fc-page-bg-color: var(--card)" in css
    assert "--fc-border-color: var(--line)" in css
    assert "data-theme=\"light\"" not in css


def test_the_events_take_their_color_with_a_fallback(app):
    css = get(app, "/static/app.css").body.decode()

    assert "border-left: 4px solid var(--ev)" in css
    assert "@supports (background: color-mix(" in css


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


def test_a_request_keeps_its_headers_without_case_and_its_body():
    request = Request.from_target(
        "POST", "/api/jobs", headers={"Content-Type": "application/json", "ORIGIN": "x"},
        body=b"{}",
    )

    assert request.headers == {"content-type": "application/json", "origin": "x"}
    assert request.body == b"{}"


# --- escribir desde la pantalla ---


class StubJobs:
    """Doble de JobsService: anota lo pedido y contesta o falla como el de verdad."""

    def __init__(self, fail=None):
        self.asked = []
        self.fail = fail

    def _answer(self, call, value):
        self.asked.append(call)
        if self.fail:
            raise self.fail
        return value

    def people(self):
        return self._answer(("people",), {"writable": True,
                                          "people": [{"chat_id": 42, "name": "Eze"}]})

    def job(self, job_id):
        return self._answer(("job", job_id), {"id": job_id, "message": "arriba"})

    def create(self, payload):
        return self._answer(("create", payload), {"id": 1, **payload})

    def update(self, job_id, payload):
        return self._answer(("update", job_id, payload), {"id": job_id, **payload})

    def delete(self, job_id):
        return self._answer(("delete", job_id), None)

    def cross_out(self, list_name, item_id):
        return self._answer(("cross_out", list_name, item_id), "leche")

    def add_items(self, list_name, text):
        return self._answer(("add_items", list_name, text), {"added": ["leche"], "repeated": []})


HOST = "192.168.68.10:8080"
JSON_HEADERS = {"Content-Type": "application/json", "Host": HOST, "Origin": f"http://{HOST}"}


@pytest.fixture
def jobs():
    return StubJobs()


@pytest.fixture
def writer(board, jobs):
    return WebApp(board, jobs=jobs)


def send(app, method, path, payload=None, headers=None):
    body = b"" if payload is None else json.dumps(payload).encode("utf-8")
    return app.handle(
        Request.from_target(method, path, headers=JSON_HEADERS if headers is None else headers,
                            body=body)
    )


def test_people_are_read_without_writing(writer, jobs):
    response = get(writer, "/api/people")

    assert response.status == 200
    assert body_json(response)["people"] == [{"chat_id": 42, "name": "Eze"}]


def test_a_job_is_read_for_the_form(writer, jobs):
    response = get(writer, "/api/jobs/7")

    assert response.status == 200
    assert jobs.asked == [("job", 7)]


def test_create_answers_201_with_the_job(writer, jobs):
    response = send(writer, "POST", "/api/jobs", {"message": "arriba"})

    assert response.status == 201
    assert body_json(response)["id"] == 1
    assert jobs.asked == [("create", {"message": "arriba"})]


def test_update_and_delete_reach_the_job_by_id(writer, jobs):
    assert send(writer, "PUT", "/api/jobs/7", {"message": "otra"}).status == 200
    assert send(writer, "DELETE", "/api/jobs/7").status == 200

    assert jobs.asked == [("update", 7, {"message": "otra"}), ("delete", 7)]


def test_an_item_is_crossed_out(writer, jobs):
    response = send(writer, "POST", "/api/lists/compras/17/done", {})

    assert response.status == 200
    assert body_json(response) == {"removed": "leche"}
    assert jobs.asked == [("cross_out", "compras", 17)]


def test_items_are_added_to_a_list(writer, jobs):
    response = send(writer, "POST", "/api/lists/compras", {"text": "leche"})

    assert response.status == 201
    assert body_json(response) == {"added": ["leche"], "repeated": []}
    assert jobs.asked == [("add_items", "compras", "leche")]


def test_a_list_only_accepts_post(writer, jobs):
    response = get(writer, "/api/lists/compras")

    assert response.status == 405
    assert response.headers["Allow"] == "POST"
    assert jobs.asked == []


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (WebError("Falta el mensaje."), 400),
        (NotFound("No existe el aviso #7."), 404),
        (ReadOnly("La pantalla es de solo lectura."), 403),
    ],
)
def test_the_service_refusals_keep_their_status_and_text(board, error, status):
    app = WebApp(board, jobs=StubJobs(fail=error))

    response = send(app, "POST", "/api/jobs", {"message": ""})

    assert response.status == status
    assert body_json(response)["error"] == str(error)


def test_a_service_that_breaks_gets_500_without_the_details(board):
    app = WebApp(board, jobs=StubJobs(fail=RuntimeError("/var/lib/domotica/jobs.db")))

    response = send(app, "POST", "/api/jobs", {"message": "x"})

    assert response.status == 500
    assert b"jobs.db" not in response.body


@pytest.mark.parametrize(
    "headers",
    [
        {"Host": HOST, "Origin": f"http://{HOST}"},
        {"Content-Type": "text/plain", "Host": HOST, "Origin": f"http://{HOST}"},
        {"Content-Type": "application/x-www-form-urlencoded", "Host": HOST},
        {"Content-Type": "application/json", "Host": HOST, "Origin": "https://malo.example"},
        {"Content-Type": "application/json", "Host": HOST, "Origin": "null"},
        {"Content-Type": "application/json", "Host": HOST,
         "Origin": "http://192.168.68.10:9999"},
        {"Content-Type": "application/json", "Origin": f"http://{HOST}"},
    ],
)
@pytest.mark.parametrize(
    ("method", "path"),
    [("POST", "/api/jobs"), ("PUT", "/api/jobs/7"), ("DELETE", "/api/jobs/7"),
     ("POST", "/api/lists/compras/17/done")],
)
def test_a_write_from_another_site_or_not_json_is_refused(writer, jobs, headers, method, path):
    response = send(writer, method, path, {"message": "arriba"}, headers=headers)

    assert response.status in (403, 415)
    assert jobs.asked == []


def test_a_write_without_origin_from_the_lan_is_accepted(writer, jobs):
    response = send(writer, "POST", "/api/jobs", {"message": "arriba"},
                    headers={"Content-Type": "application/json; charset=utf-8", "Host": HOST})

    assert response.status == 201


@pytest.mark.parametrize("body", [b"", b"no es json", b"[1, 2]", b"\xff"])
def test_a_body_that_is_not_a_json_object_gets_400(writer, jobs, body):
    response = writer.handle(Request.from_target("POST", "/api/jobs", headers=JSON_HEADERS,
                                                 body=body))

    assert response.status == 400
    assert jobs.asked == []


@pytest.mark.parametrize(
    ("method", "path", "allow"),
    [
        ("PATCH", "/api/jobs/7", "GET, PUT, DELETE"),
        ("GET", "/api/jobs", "POST"),
        ("POST", "/api/people", "GET"),
        ("GET", "/api/lists/compras/17/done", "POST"),
    ],
)
def test_the_wrong_method_gets_405(writer, method, path, allow):
    response = send(writer, method, path, {})

    assert response.status == 405
    assert response.headers["Allow"] == allow


@pytest.mark.parametrize(
    "path", ["/api/jobs/abc", "/api/jobs/7/8", "/api/lists/compras/x/done", "/api/lists/compras/17"]
)
def test_a_malformed_id_gets_404(writer, jobs, path):
    assert send(writer, "POST", path, {}).status in (404, 405)
    assert jobs.asked == []


def test_without_the_service_the_screen_cannot_write(app):
    assert send(app, "POST", "/api/jobs", {"message": "x"}).status == 405
    assert get(app, "/api/people").status == 200
    assert body_json(get(app, "/api/people")) == {"writable": False, "people": [], "devices": []}


def test_writes_carry_no_cors_headers(writer):
    response = send(writer, "POST", "/api/jobs", {"message": "arriba"})

    assert not any(name.lower().startswith("access-control") for name in response.headers)
