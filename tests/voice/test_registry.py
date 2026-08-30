import uuid

import pytest

from homeauto.voice.registry import SpeakerRegistry, UnknownDevice

NEST = uuid.UUID("d17e8311-d82e-5116-8f58-6292603bbc1b")
TV = uuid.UUID("083e8ba4-67d7-e2d1-ac92-dcdd281d93bc")
DEVICES = {"parlante": NEST, "tv": TV}


def build_registry():
    built = []

    def build(device_uuid):
        built.append(device_uuid)
        return f"speaker-{device_uuid}"

    return SpeakerRegistry(DEVICES, build=build), built


def test_returns_a_speaker_per_alias():
    registry, _ = build_registry()

    assert registry.get("parlante") == f"speaker-{NEST}"
    assert registry.get("tv") == f"speaker-{TV}"


def test_each_speaker_is_built_once():
    registry, built = build_registry()

    registry.get("parlante")
    registry.get("parlante")

    assert built == [NEST], "conectarse al dispositivo es caro: no rehacerlo por mensaje"


def test_aliases_are_case_insensitive():
    registry, _ = build_registry()

    assert registry.get("TV") == registry.get("tv")


def test_unknown_alias_says_what_there_is():
    registry, _ = build_registry()

    with pytest.raises(UnknownDevice) as caught:
        registry.get("cocina")

    assert "cocina" in str(caught.value)
    assert "parlante" in str(caught.value) and "tv" in str(caught.value)


def test_lists_its_aliases_in_order():
    registry, _ = build_registry()

    assert registry.aliases == ["parlante", "tv"]


def test_knows_what_it_has():
    registry, _ = build_registry()

    assert registry.has("tv") is True
    assert registry.has("cocina") is False


def test_nothing_is_built_until_asked():
    _, built = build_registry()

    assert built == [], "no conectarse a todos los equipos al arrancar"
