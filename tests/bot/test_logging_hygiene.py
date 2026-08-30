import logging

import pytest

from homeauto import main


def test_httpx_never_logs_at_info(monkeypatch):
    """The Telegram API URL carries the token: httpx at INFO leaks it to the journal."""
    logging.getLogger("httpx").setLevel(logging.NOTSET)

    def explode(_path):
        raise RuntimeError("corte deliberado, ya pasamos por el setup de logging")

    monkeypatch.setattr(main.Config, "from_file", staticmethod(explode))

    with pytest.raises(RuntimeError):
        main.main()

    for noisy in ("httpx", "httpcore"):
        assert logging.getLogger(noisy).level >= logging.WARNING, f"{noisy} filtra el token"
