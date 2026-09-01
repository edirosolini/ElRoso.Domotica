"""Lo que el código importa tiene que estar declarado.

🔴 `requests` funcionaba en el contenedor sin estar en requirements.txt: lo
arrastraba `casttube`, que es dependencia de pychromecast. Cinco módulos lo
importan directo —clima, agenda, monitor, Seq y pulido— y todos lo hacen
adentro de la función, así que el día que esa cadena cambie no falla el
arranque: falla el primer comando que alguien use, de a uno.
"""

import ast
import sys
from importlib.metadata import packages_distributions
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

# El paquete propio y lo que se invoca como subproceso, no como import.
PROPIOS = {"homeauto"}


def top_level_imports() -> set[str]:
    found: set[str] = set()
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                found.add(node.module.split(".")[0])
    return found


def declared() -> set[str]:
    """The requirement names, normalized the way pip compares them."""
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    names = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # "python-telegram-bot[job-queue]>=20" -> "python-telegram-bot"
        name = line.split("[")[0].split("=")[0].split(">")[0].split("<")[0].split(";")[0]
        names.add(name.strip().lower().replace("_", "-"))
    return names


def third_party() -> set[str]:
    return {
        name for name in top_level_imports()
        if name not in sys.stdlib_module_names and name not in PROPIOS
    }


def test_there_is_something_to_check():
    assert third_party(), "el escaneo no encontró ningún import de terceros"


@pytest.mark.parametrize("module", sorted(third_party()))
def test_every_imported_package_is_declared(module):
    """Un import que anda solo porque otro paquete lo arrastra es una bomba de tiempo."""
    distributions = packages_distributions().get(module)
    if not distributions:
        pytest.skip(f"{module} no está instalado en este entorno")

    posibles = {dist.lower().replace("_", "-") for dist in distributions}
    assert posibles & declared(), (
        f"src importa '{module}' (lo trae {', '.join(sorted(posibles))}) "
        f"y no está en requirements.txt"
    )
