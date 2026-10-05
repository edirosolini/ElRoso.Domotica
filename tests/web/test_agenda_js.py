"""La lógica pura de la agenda y del kiosco, corrida con node si está instalado."""

import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
HERE = Path(__file__).parent


@pytest.mark.skipif(NODE is None, reason="sin node no se corre la lógica de la pantalla")
@pytest.mark.parametrize("script", ["agenda_logic.js", "kiosk_logic.js"])
def test_the_screen_logic_passes_in_node(script):
    done = subprocess.run([NODE, str(HERE / script)], capture_output=True, text=True, timeout=30)

    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "ok"
