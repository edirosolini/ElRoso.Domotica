"""Shared helpers. Building a Config lives here so a field change touches one place."""

import uuid

from homeauto.config import Config

NEST_UUID = uuid.UUID("d17e8311-d82e-5116-8f58-6292603bbc1b")


def make_config(allowed=(), devices=None, default="parlante", token="123:ABC"):
    return Config(
        telegram_token=token,
        devices=devices or {"parlante": NEST_UUID},
        default_device=default,
        allowed_chat_ids=frozenset(allowed),
    )


class FakeSpeaker:
    """Records what it was asked to do, and can be told to fail."""

    def __init__(self, name="parlante", fail=None):
        self.name = name
        self.said = []
        self.floors = []
        self.volumes = []
        self.stopped = 0
        self.fail = fail

    def say(self, text, min_volume=None):
        if self.fail:
            raise self.fail
        self.said.append(text)
        self.floors.append(min_volume)

    def set_volume(self, percent):
        if self.fail:
            raise self.fail
        self.volumes.append(percent)

    def stop(self):
        self.stopped += 1

    def device_name(self):
        if self.fail:
            raise self.fail
        return f"Equipo {self.name}"


def make_registry(**speakers):
    """A SpeakerRegistry over ready-made fakes, keyed by alias."""
    from homeauto.voice.registry import SpeakerRegistry

    if not speakers:
        speakers = {"parlante": FakeSpeaker()}
    devices = {alias: NEST_UUID for alias in speakers}
    return SpeakerRegistry(devices, build=lambda _uuid: None), speakers


class StubRegistry:
    """Simpler than wiring uuids: maps alias straight to a fake speaker."""

    def __init__(self, **speakers):
        self._speakers = speakers or {"parlante": FakeSpeaker()}

    @property
    def aliases(self):
        return list(self._speakers)

    def has(self, alias):
        return alias.strip().lower() in self._speakers

    def get(self, alias):
        from homeauto.voice.registry import UnknownDevice

        alias = alias.strip().lower()
        if alias not in self._speakers:
            raise UnknownDevice(f"No conozco '{alias}'. Tengo: {', '.join(self._speakers)}")
        return self._speakers[alias]
