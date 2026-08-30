import logging

from homeauto import main


def test_httpx_never_logs_at_info(monkeypatch):
    """The Telegram API URL carries the token: httpx at INFO leaks it to the journal."""
    logging.getLogger("httpx").setLevel(logging.NOTSET)
    monkeypatch.setattr(main, "build_commands", lambda: (_ for _ in ()).throw(RuntimeError("corte")))

    try:
        main.main()
    except RuntimeError:
        pass

    assert logging.getLogger("httpx").level >= logging.WARNING
