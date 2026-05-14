import sys
import types


def test_transcribe_rejects_tiny_payload():
    from utils.voice_pref import transcribe_wav_bytes

    text, err = transcribe_wav_bytes(b"short")
    assert text is None
    assert err and "too short" in err.lower()


def test_transcribe_success_with_mocked_speech_recognition(monkeypatch):
    class _AF:
        def __init__(self, buf):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class _Rec:
        def record(self, source):
            return object()

        def recognize_google(self, audio):
            return "  prefer morning labs  "

    fake = types.ModuleType("speech_recognition")
    fake.Recognizer = lambda: _Rec()
    fake.AudioFile = _AF
    fake.UnknownValueError = type("UnknownValueError", (Exception,), {})
    fake.RequestError = type("RequestError", (Exception,), {})

    monkeypatch.setitem(sys.modules, "speech_recognition", fake)

    from utils.voice_pref import transcribe_wav_bytes

    data = b"\x00" * 400
    text, err = transcribe_wav_bytes(data)
    assert err is None
    assert text == "prefer morning labs"
