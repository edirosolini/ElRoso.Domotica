from datetime import datetime, timedelta, timezone

import pytest

from homeauto.watch.seq import SeqClient, SeqError, summarize

NOW = datetime(2026, 8, 30, 10, 0, tzinfo=timezone.utc)


def event(message, level="Error", when=NOW, exception=None):
    payload = {
        "Timestamp": when.isoformat(),
        "Level": level,
        "RenderedMessage": message,
    }
    if exception:
        payload["Exception"] = exception
    return payload


def client(payload=None, boom=None, status=200):
    calls = []

    def fetch(url, headers, params):
        calls.append({"url": url, "headers": headers, "params": params})
        if boom:
            raise boom
        return status, payload if payload is not None else []

    built = SeqClient(base_url="http://172.68.0.7", api_key="clave", fetch=fetch)
    built.calls = calls
    return built


def test_it_asks_only_for_errors_and_worse():
    seq = client()

    seq.errors_since(NOW - timedelta(minutes=5))

    filter_used = seq.calls[0]["params"].get("filter", "")
    assert "Error" in filter_used or "@Level" in filter_used


def test_it_sends_the_api_key():
    seq = client()

    seq.errors_since(NOW - timedelta(minutes=5))

    assert seq.calls[0]["headers"].get("X-Seq-ApiKey") == "clave"


def test_it_bounds_the_query_by_time():
    seq = client()
    since = NOW - timedelta(minutes=5)

    seq.errors_since(since)

    params = seq.calls[0]["params"]
    assert any("2026-08-30" in str(value) for value in params.values())


def test_it_reads_the_events():
    seq = client([event("Se cayó la conexión a la base"), event("Timeout llamando a ARCA")])

    found = seq.errors_since(NOW - timedelta(minutes=5))

    assert len(found) == 2
    assert found[0].message == "Se cayó la conexión a la base"
    assert found[0].level == "Error"


def test_it_survives_a_different_field_name():
    """No verifiqué los nombres exactos contra la instancia real: no romper por eso."""
    seq = client([{"Timestamp": NOW.isoformat(), "Level": "Fatal", "Message": "otro nombre"}])

    found = seq.errors_since(NOW - timedelta(minutes=5))

    assert found[0].message == "otro nombre"


def test_an_event_without_a_message_does_not_crash():
    seq = client([{"Timestamp": NOW.isoformat(), "Level": "Error"}])

    found = seq.errors_since(NOW - timedelta(minutes=5))

    assert len(found) == 1
    assert found[0].message


def test_an_unauthorized_answer_says_it_is_the_key():
    seq = client(status=401)

    with pytest.raises(SeqError, match="clave"):
        seq.errors_since(NOW - timedelta(minutes=5))


def test_a_network_failure_is_reported():
    seq = client(boom=TimeoutError("sin ruta"))

    with pytest.raises(SeqError):
        seq.errors_since(NOW - timedelta(minutes=5))


def test_an_answer_that_is_not_a_list_is_reported():
    seq = client(payload={"no": "es una lista"})

    with pytest.raises(SeqError):
        seq.errors_since(NOW - timedelta(minutes=5))


def test_nothing_wrong_summarizes_to_nothing():
    assert summarize([]) is None


def test_one_error_reads_naturally():
    summary = summarize([_as_event("Se cayó la base")])

    assert summary.spoken == "Hay un error nuevo en Seq."
    assert "Se cayó la base" in summary.detail


def test_many_errors_are_counted_and_only_one_is_quoted():
    events = [_as_event(f"error {i}") for i in range(7)]

    summary = summarize(events)

    assert summary.spoken == "Hay siete errores nuevos en Seq."
    assert summary.detail.count("error 0") + summary.detail.count("error 6") == 1, "solo se cita uno"


def test_a_very_long_message_is_cut():
    summary = summarize([_as_event("x" * 900)])

    assert len(summary.detail) < 400


def test_the_spoken_half_never_carries_a_digit():
    """El texto hablado se sintetiza; la cita del log queda solo escrita."""
    events = [_as_event("Timeout tras 30s en /api/v2") for _ in range(21)]

    summary = summarize(events)

    assert not any(char.isdigit() for char in summary.spoken)
    assert "30s" in summary.detail


def _as_event(message):
    from homeauto.watch.seq import SeqEvent

    return SeqEvent(timestamp=NOW, level="Error", message=message)


def test_the_summary_says_which_seq_it_is():
    """Con dos VPS, "hay errores en Seq" no dice en cuál."""
    summary = summarize([_as_event("Se cayó la base")], source="Seq de hosting")

    assert summary.spoken == "Hay un error nuevo en Seq de hosting."


def test_the_source_has_a_default():
    """La instancia de siempre sigue diciendo lo mismo que decía."""
    assert summarize([_as_event("x")]).spoken == "Hay un error nuevo en Seq."
