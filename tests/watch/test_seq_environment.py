"""Un error sin ambiente ni app no dice si hay que salir corriendo."""

from datetime import datetime

from homeauto.watch.seq import SeqClient, SeqEvent, summarize


def event(app="Facturador.Backend", env="Production", message="explotó", minute=0):
    return SeqEvent(
        timestamp=datetime(2026, 9, 21, 20, minute),
        level="Error",
        message=message,
        application=app,
        environment=env,
    )


def payload(app="Staging-Facturador.Backend", env="Staging"):
    return {
        "Timestamp": "2026-09-21T20:00:00.0000000Z",
        "Level": "Error",
        "RenderedMessage": "explotó",
        "Properties": [
            {"Name": "ApplicationName", "Value": app},
            {"Name": "EnvironmentName", "Value": env},
            {"Name": "MachineName", "Value": "807b0e9e5eef"},
        ],
    }


def test_the_event_carries_the_app_and_the_environment():
    parsed = SeqClient._to_event(payload())

    assert parsed.application == "Staging-Facturador.Backend"
    assert parsed.environment == "Staging"


def test_an_event_without_those_properties_does_not_break():
    parsed = SeqClient._to_event({"RenderedMessage": "algo", "Level": "Error"})

    assert parsed.application == ""
    assert parsed.environment == ""


def test_production_is_said_first_and_by_name():
    summary = summarize([event(), event(minute=1)], source="Seq de vps")

    assert "producción" in summary.spoken.lower()
    assert "Facturador Backend" in summary.spoken


def test_staging_says_it_is_staging():
    summary = summarize([event(env="Staging")], source="Seq de vps")

    assert "producción" not in summary.spoken.lower()
    assert "prueba" in summary.spoken.lower()


def test_the_app_name_drops_the_environment_prefix_and_the_dots():
    """«Staging-Facturador.Backend» dicho tal cual es ilegible."""
    summary = summarize([event(app="Staging-Facturador.Backend", env="Staging")])

    assert "Facturador Backend" in summary.spoken
    assert "Facturador.Backend" not in summary.spoken
    assert "Staging-" not in summary.spoken


def test_what_is_said_never_carries_a_digit():
    summary = summarize([event() for _ in range(3)])

    assert not any(c.isdigit() for c in summary.spoken)


def test_several_apps_are_told_apart():
    summary = summarize([
        event(app="Facturador.Backend", env="Production"),
        event(app="Portal.Web", env="Staging"),
    ])

    assert "Facturador Backend" in summary.spoken
    assert "Portal Web" in summary.spoken


def test_production_leads_even_when_staging_has_more_errors():
    """Lo que importa primero es el fuego, no el volumen."""
    summary = summarize(
        [event(app="Portal.Web", env="Staging") for _ in range(5)]
        + [event(app="Facturador.Backend", env="Production")]
    )

    assert summary.spoken.lower().index("producción") < summary.spoken.lower().index("prueba")


def test_the_detail_keeps_the_environment_and_the_app_for_reading():
    summary = summarize([event(message="System.ArgumentOutOfRangeException: 1.24s")])

    assert "Production" in summary.detail
    assert "Facturador.Backend" in summary.detail
    assert "ArgumentOutOfRange" in summary.detail


def test_events_without_an_app_still_produce_a_summary():
    summary = summarize([SeqEvent(timestamp=None, level="Error", message="pum")], source="Seq")

    assert summary is not None
    assert "error" in summary.spoken.lower()


def test_an_event_without_an_environment_is_not_painted_as_staging():
    summary = summarize([SeqEvent(timestamp=None, level="Error", message="pum")])

    assert "🧪" not in summary.detail
    assert "🔥" not in summary.detail
