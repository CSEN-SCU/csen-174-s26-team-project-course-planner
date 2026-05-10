"""Optional speech-to-text for planner preference text (Google web API via SpeechRecognition)."""

from __future__ import annotations

import io
from typing import Optional, Tuple


def transcribe_wav_bytes(data: bytes) -> tuple[Optional[str], Optional[str]]:
    """Return ``(transcript, error_message)``. On success ``error_message`` is None.

    Expects WAV bytes (e.g. from ``st.audio_input``). Requires network access for
    ``recognize_google`` and the ``SpeechRecognition`` package.
    """
    if not data or len(data) < 200:
        return None, "Recording too short or empty—try a few seconds of speech."

    try:
        import speech_recognition as sr
    except ModuleNotFoundError:
        return None, "Voice input needs the SpeechRecognition package (see requirements.txt)."

    try:
        r = sr.Recognizer()
        with sr.AudioFile(io.BytesIO(data)) as source:
            audio = r.record(source)
        text = r.recognize_google(audio)
        out = (text or "").strip()
        return (out or None), None
    except sr.UnknownValueError:
        return None, "Could not understand the audio; try speaking more clearly."
    except sr.RequestError as e:
        return None, f"Speech recognition service error: {e}"
    except OSError as e:
        return None, f"Could not read audio: {e}"
    except Exception as e:  # pragma: no cover - defensive
        return None, str(e)
