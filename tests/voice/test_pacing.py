"""El ritmo con que habla la casa.

Piper se llamaba sin un solo parámetro, así que la casa hablaba con los valores
de fábrica y **sin pausa entre oraciones**. Un chiste salía con el remate pegado
al setup, y se escuchaba como si fuera acelerado.
"""

from pathlib import Path

from homeauto.voice.tts import PiperRunner, VoiceSynth


class FakeRun:
    """Reemplaza subprocess.run, guardando el comando que se armó."""

    def __init__(self):
        self.commands = []

    def __call__(self, command, **kwargs):
        self.commands.append(command)
        return type("Done", (), {"returncode": 0, "stderr": ""})()


def build(**pacing):
    run = FakeRun()
    runner = PiperRunner("/usr/bin/python", "/voces/daniela.onnx", run=run, **pacing)
    runner("hola", Path("/tmp/x.wav"))
    return run.commands[0]


def test_by_default_it_breathes_between_sentences():
    """🔴 La pausa de fábrica es cero y pega el remate con el setup."""
    command = build()

    assert "--sentence-silence" in command
    assert float(command[command.index("--sentence-silence") + 1]) > 0


def test_by_default_it_is_not_rushed():
    command = build()

    assert "--length-scale" in command
    assert float(command[command.index("--length-scale") + 1]) > 1.0


def test_each_knob_can_be_moved():
    command = build(length_scale=1.4, sentence_silence=0.9, noise_scale=0.5, noise_w=0.7)

    for flag, value in (("--length-scale", "1.4"), ("--sentence-silence", "0.9"),
                        ("--noise-scale", "0.5"), ("--noise-w-scale", "0.7")):
        assert flag in command, f"falta {flag}"
        assert command[command.index(flag) + 1] == value


def test_a_knob_left_alone_is_not_passed():
    """Lo que no se configura lo decide el modelo, no un default nuestro."""
    command = build(noise_scale=None, noise_w=None)

    assert "--noise-scale" not in command
    assert "--noise-w-scale" not in command


# --- 🔴 el cache -----------------------------------------------------------


def test_the_pacing_belongs_in_the_cache_key(tmp_path):
    """Si no, cambiar la entonación deja sonando la versión vieja de toda frase ya dicha.

    Es exactamente el bug que ya pasó una vez con la voz.
    """
    lenta = VoiceSynth(tmp_path, runner=lambda t, p: None, voice="daniela", pacing="lenta")
    rapida = VoiceSynth(tmp_path, runner=lambda t, p: None, voice="daniela", pacing="rapida")

    assert lenta._key("hola") != rapida._key("hola")


def test_the_same_pacing_still_reuses_the_cache(tmp_path):
    uno = VoiceSynth(tmp_path, runner=lambda t, p: None, voice="daniela", pacing="lenta")
    otro = VoiceSynth(tmp_path, runner=lambda t, p: None, voice="daniela", pacing="lenta")

    assert uno._key("hola") == otro._key("hola")


# --- el cableado ------------------------------------------------------------


def test_the_wiring_hands_the_pacing_to_the_cache(tmp_path):
    """🔴 Si el runner y el cache no comparten la entonación, el cache miente:
    se sintetiza con un ritmo y se reusa audio hecho con otro."""
    from homeauto import main

    synth = main.build_synth(tmp_path / "cache")

    assert synth.pacing == synth.runner.pacing
    assert synth.pacing, "la entonación no llegó a la clave del cache"


def test_the_pacing_can_be_moved_from_the_environment(monkeypatch):
    from homeauto import main

    monkeypatch.setenv("DOMOTICA_LENGTH_SCALE", "1.4")
    monkeypatch.setenv("DOMOTICA_SENTENCE_SILENCE", "0.8")
    knobs = main.pacing_from_env()

    assert knobs["length_scale"] == 1.4
    assert knobs["sentence_silence"] == 0.8


def test_an_unset_knob_keeps_its_default(monkeypatch):
    from homeauto import main

    monkeypatch.delenv("DOMOTICA_LENGTH_SCALE", raising=False)
    monkeypatch.delenv("DOMOTICA_NOISE_SCALE", raising=False)
    knobs = main.pacing_from_env()

    assert knobs["length_scale"] > 1.0, "el default arreglado, no el de fábrica"
    assert knobs["noise_scale"] is None, "lo que no se toca lo decide el modelo"
