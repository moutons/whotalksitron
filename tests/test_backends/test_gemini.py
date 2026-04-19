from pathlib import Path

from whotalksitron.backends.gemini import GeminiBackend, _build_prompt, _parse_response
from whotalksitron.config import Config
from whotalksitron.models import SpeakerPool


def _make_config(**overrides) -> Config:
    cfg = Config()
    cfg.gemini_api_key = "test-key"
    cfg.gemini_model = "gemini-2.5-flash"
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def test_gemini_is_available_with_key():
    cfg = _make_config()
    backend = GeminiBackend(cfg)
    assert backend.is_available()


def test_gemini_not_available_without_key():
    cfg = _make_config(gemini_api_key="", gemini_use_adc=False)
    backend = GeminiBackend(cfg)
    assert not backend.is_available()


def test_gemini_supports_diarization():
    backend = GeminiBackend(_make_config())
    assert backend.supports_diarization()


def test_build_prompt_no_speakers():
    prompt = _build_prompt(speakers=None)
    assert "transcribe" in prompt.lower()
    assert "speaker" in prompt.lower()


def test_build_prompt_with_speakers():
    pool = SpeakerPool(
        podcast="atp",
        speakers={"matt": [Path("/s/matt1.wav")]},
    )
    prompt = _build_prompt(speakers=pool)
    assert "matt" in prompt.lower()


def test_parse_response_basic():
    response_text = (
        "[00:00:00] Matt: Welcome to the show.\n"
        "[00:00:05] Casey: Thanks for having me.\n"
        "[00:00:10] Matt: Let's dive in.\n"
    )
    segments = _parse_response(response_text)
    assert len(segments) == 3
    assert segments[0].speaker == "Matt"
    assert segments[0].text == "Welcome to the show."
    assert segments[0].start == 0.0
    assert segments[1].speaker == "Casey"
    assert segments[1].start == 5.0
    assert segments[2].speaker == "Matt"
    assert segments[2].start == 10.0


def test_parse_response_no_speaker():
    response_text = "[00:00:00] Hello world.\n"
    segments = _parse_response(response_text)
    assert len(segments) == 1
    assert segments[0].speaker is None
    assert segments[0].text == "Hello world."


def test_parse_response_colon_in_text_not_speaker():
    response_text = "[00:00:00] Matt: Note: this is important.\n"
    segments = _parse_response(response_text)
    assert len(segments) == 1
    assert segments[0].speaker == "Matt"
    assert segments[0].text == "Note: this is important."


def test_parse_response_no_speaker_with_colon():
    response_text = "[00:00:00] Note: this is important.\n"
    segments = _parse_response(response_text)
    assert len(segments) == 1
    assert segments[0].speaker is None
    assert segments[0].text == "Note: this is important."


def test_parse_response_hour_timestamps():
    response_text = "[01:23:45] Speaker 01: Long episode.\n"
    segments = _parse_response(response_text)
    assert segments[0].start == 5025.0
    assert segments[0].speaker == "Speaker 01"
