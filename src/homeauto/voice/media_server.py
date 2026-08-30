"""Tiny HTTP server that publishes the synthesized audio to the speaker.

A cast device does not receive a file: it receives a URL and fetches it itself.
So whoever casts has to be reachable by the speaker on this port.
"""

from __future__ import annotations

import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):  # noqa: D102 - one line per fetch is noise
        pass


class MediaServer:
    """Serves one directory, and knows the URL the speaker should ask for."""

    def __init__(self, directory: Path | str, advertised_ip: str, port: int = 8765):
        self.directory = Path(directory)
        self.advertised_ip = advertised_ip
        self._requested_port = port
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        if self._server is None:
            return self._requested_port
        return self._server.server_address[1]

    def start(self) -> None:
        if self._server is not None:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        handler = partial(_QuietHandler, directory=str(self.directory))
        self._server = ThreadingHTTPServer(("0.0.0.0", self._requested_port), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def url_for(self, filename: str) -> str:
        return f"http://{self.advertised_ip}:{self.port}/{filename}"

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        self._server = None
        self._thread = None
