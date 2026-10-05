"""La lógica pura de la agenda, corrida con node si está instalado."""

import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
SCRIPT = Path(__file__).with_name("agenda_logic.js")


@pytest.mark.skipif(NODE is None, reason="sin node no se corre la lógica de la agenda")
def test_the_agenda_logic_passes_in_node():
    done = subprocess.run([NODE, str(SCRIPT)], capture_output=True, text=True, timeout=30)

    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "ok"
