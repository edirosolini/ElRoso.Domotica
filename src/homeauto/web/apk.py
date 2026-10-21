"""Las apps que la casa ofrece para bajar, leídas del disco en cada pedido."""

from __future__ import annotations

from pathlib import Path

# Lo único que se sirve: un nombre fuera de la lista no toca el disco.
FILES = ("tele.apk", "tele.json")


class AppShelf:
    """Los archivos de `FILES` dentro de un directorio."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)

    def get(self, name: str) -> bytes | None:
        """Los bytes del archivo; None si no está en la lista o no existe."""
        if name not in FILES:
            return None
        try:
            return (self.directory / name).read_bytes()
        except FileNotFoundError:
            return None
