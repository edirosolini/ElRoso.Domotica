"""Una nota de voz: se transcribe y entra por donde entra el texto suelto."""

from pathlib import Path

from homeauto.bot.commands import Commands
from homeauto.listen import ListenError
from homeauto.route import Decision

from tests.conftest import FakeSpeaker, StubRegistry, make_config
from tests.bot.test_free_text import FakeAsker, FakeRouter, FakeWeather

OWNER = 42
INTRUSO = 99
AUDIO = b"OggS\x00fake"


class FakeTranscriber:
    def __init__(self, heard="cómo viene el tiempo", boom=None):
        self.heard = heard
        self.boom = boom
        self.calls = []

    def __call__(self, audio, mime="audio/ogg"):
        self.calls.append((audio, mime))
        if self.boom:
            raise self.boom
        return self.heard


class FakeVoicemail:
    def __init__(self, tmp_path=None, boom=None):
        self.said = []
        self.boom = boom
        self.tmp_path = tmp_path

    def __call__(self, text):
        self.said.append(text)
        if self.boom:
            raise self.boom
        path = (self.tmp_path or Path("/tmp")) / "respuesta.ogg"
        path.write_bytes(b"OggS")
        return path


def build(transcribe=None, router=None, voicemail=None):
    speakers = {"parlante": FakeSpeaker("parlante")}
    commands = Commands(
        config=make_config(allowed={OWNER}, devices=dict.fromkeys(speakers)),
        speakers=StubRegistry(**speakers),
        weather=FakeWeather(),
        asker=FakeAsker(),
        router=router if router is not None else FakeRouter(),
        transcribe=transcribe if transcribe is not None else FakeTranscriber(),
        voicemail=voicemail,
    )
    return commands, speakers


def test_what_was_said_runs_the_command_it_meant():
    cmd, _ = build(router=FakeRouter(Decision("clima")))

    reply = cmd.heard(OWNER, AUDIO)

    assert "catorce grados" in reply.text


def test_the_reply_shows_what_it_understood_hearing():
    cmd, _ = build(
        transcribe=FakeTranscriber("bajá el volumen a cuarenta"),
        router=FakeRouter(Decision("volumen", "40")),
    )

    reply = cmd.heard(OWNER, AUDIO)

    assert "bajá el volumen a cuarenta" in reply.text
    assert "/volumen 40" in reply.text


def test_an_audio_it_cannot_hear_says_so_and_runs_nothing():
    cmd, spk = build(transcribe=FakeTranscriber(boom=ListenError("no entendí lo que dice")))

    reply = cmd.heard(OWNER, AUDIO)

    assert "no entendí" in reply.text.lower()
    assert spk["parlante"].said == []


def test_without_a_transcriber_it_says_it_does_not_listen():
    cmd, _ = build()
    cmd.transcribe = None

    assert "audio" in cmd.heard(OWNER, AUDIO).text.lower()


def test_a_stranger_is_turned_away_before_paying_the_model():
    transcribe = FakeTranscriber()
    cmd, _ = build(transcribe=transcribe)

    reply = cmd.heard(INTRUSO, AUDIO)

    assert "No estás en la lista" in reply.text
    assert transcribe.calls == []


# --- la respuesta vuelve por donde entró ------------------------------

def test_an_audio_is_answered_with_an_audio(tmp_path):
    mail = FakeVoicemail(tmp_path)
    cmd, _ = build(voicemail=mail)

    reply = cmd.heard(OWNER, AUDIO)

    assert reply.audio is not None
    assert mail.said, "no se grabó la respuesta"


def test_an_audio_does_not_wake_the_speaker_by_itself(tmp_path):
    cmd, spk = build(voicemail=FakeVoicemail(tmp_path))

    cmd.heard(OWNER, AUDIO)

    assert spk["parlante"].said == [], "el parlante se pide, no es el default"


def test_an_audio_that_asks_for_the_speaker_gets_both(tmp_path):
    cmd, spk = build(
        transcribe=FakeTranscriber("cómo viene el clima por el parlante"),
        voicemail=FakeVoicemail(tmp_path),
    )

    reply = cmd.heard(OWNER, AUDIO)

    assert spk["parlante"].said == ["Ahora hay catorce grados."]
    assert reply.audio is not None, "igual vuelve por donde entró"


def test_the_written_answer_is_never_lost(tmp_path):
    cmd, _ = build(voicemail=FakeVoicemail(tmp_path))

    reply = cmd.heard(OWNER, AUDIO)

    assert "🎤" in reply.text


def test_a_voicemail_that_fails_still_answers_in_writing(tmp_path):
    from homeauto.voice.voicemail import VoicemailError

    mail = FakeVoicemail(tmp_path, boom=VoicemailError("opusenc no está"))
    cmd, _ = build(voicemail=mail)

    reply = cmd.heard(OWNER, AUDIO)

    assert reply.audio is None
    assert reply.text


def test_without_a_voicemail_wired_it_only_writes(tmp_path):
    cmd, _ = build()

    reply = cmd.heard(OWNER, AUDIO)

    assert reply.audio is None
    assert reply.text


def test_the_voice_note_does_not_read_back_what_you_said(tmp_path):
    """Grabar la respuesta entera le devolvía «Entendí barra clima»."""
    mail = FakeVoicemail(tmp_path)
    cmd, _ = build(
        transcribe=FakeTranscriber("cómo viene el clima"),
        router=FakeRouter(Decision("clima")),
        voicemail=mail,
    )

    reply = cmd.heard(OWNER, AUDIO)

    grabado = mail.said[0]
    assert "Entendí" not in grabado
    assert "/clima" not in grabado
    assert "cómo viene el clima" not in grabado
    assert "catorce grados" in grabado
    assert "Entendí: /clima" in reply.text, "escrito sí se ve qué entendió"


def test_a_question_is_recorded_with_the_half_made_to_be_heard(tmp_path):
    """La mitad escrita trae «500 g» y Piper lee «quinientos ge»."""
    from homeauto.ask import Answer

    class RecipeAsker:
        def ask(self, question):
            return Answer(
                spoken="Dorá la carne, sumá el tomate y cociná tapado.",
                written="Dorá 500 g de carne. Agregá 500 g de tomate. Cociná 45 minutos.",
            )

    mail = FakeVoicemail(tmp_path)
    speakers = {"parlante": FakeSpeaker("parlante")}
    cmd = Commands(
        config=make_config(allowed={OWNER}, devices=dict.fromkeys(speakers)),
        speakers=StubRegistry(**speakers),
        asker=RecipeAsker(),
        router=FakeRouter(Decision(None)),
        transcribe=FakeTranscriber("cómo hago tallarines con tuco"),
        voicemail=mail,
    )

    reply = cmd.heard(OWNER, AUDIO)

    grabado = mail.said[0]
    assert not any(c.isdigit() for c in grabado), f"dígitos en el audio: {grabado}"
    assert "500" in reply.text, "lo escrito conserva la receta entera"


def test_an_answer_full_of_digits_is_not_recorded(tmp_path):
    """Un audio que se lee mal es peor que un texto: vuelve escrito."""

    class DigitWeather:
        def spoken(self):
            return "Ahora hay 14 grados, mínima de 9."

    mail = FakeVoicemail(tmp_path)
    speakers = {"parlante": FakeSpeaker("parlante")}
    cmd = Commands(
        config=make_config(allowed={OWNER}, devices=dict.fromkeys(speakers)),
        speakers=StubRegistry(**speakers),
        weather=DigitWeather(),
        router=FakeRouter(Decision("clima")),
        transcribe=FakeTranscriber("cómo viene el clima"),
        voicemail=mail,
    )

    reply = cmd.heard(OWNER, AUDIO)

    assert mail.said == []
    assert reply.audio is None
    assert reply.text


def test_an_answer_that_cannot_be_said_comes_back_in_writing(tmp_path):
    """Grabar «te lo dejé escrito en el chat» sin mandar el chat es una burla."""
    from homeauto.ask import NOT_SPOKEN, Answer

    class UnsayableAsker:
        def ask(self, question):
            return Answer(spoken=NOT_SPOKEN, written="El top diez: 1) uno, 2) dos...")

    mail = FakeVoicemail(tmp_path)
    speakers = {"parlante": FakeSpeaker("parlante")}
    cmd = Commands(
        config=make_config(allowed={OWNER}, devices=dict.fromkeys(speakers)),
        speakers=StubRegistry(**speakers),
        asker=UnsayableAsker(),
        router=FakeRouter(Decision(None)),
        transcribe=FakeTranscriber("dame el top diez"),
        voicemail=mail,
    )

    reply = cmd.heard(OWNER, AUDIO)

    assert mail.said == []
    assert reply.audio is None
    assert "top diez" in reply.text
