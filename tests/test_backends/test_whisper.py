from whotalksitron.backends.whisper import WhisperBackend, _parse_whisper_response
from whotalksitron.config import Config


def _make_config(**overrides) -> Config:
    cfg = Config()
    cfg.whisper_endpoint = "http://localhost:1234/v1"
    cfg.whisper_model = "whisper-large-v3"
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def test_whisper_does_not_support_diarization():
    backend = WhisperBackend(_make_config())
    assert not backend.supports_diarization()


def test_parse_whisper_response_verbose_json():
    response_data = {
        "segments": [
            {"start": 0.0, "end": 5.0, "text": " Hello world."},
            {"start": 5.0, "end": 12.5, "text": " How are you?"},
        ]
    }
    segments = _parse_whisper_response(response_data)
    assert len(segments) == 2
    assert segments[0].text == "Hello world."
    assert segments[0].start == 0.0
    assert segments[0].end == 5.0
    assert segments[0].speaker is None
    assert segments[1].text == "How are you?"


def test_parse_whisper_response_empty():
    segments = _parse_whisper_response({"segments": []})
    assert len(segments) == 0


def test_parse_whisper_response_no_segments_key():
    segments = _parse_whisper_response({"text": "just text"})
    assert len(segments) == 1
    assert segments[0].text == "just text"
    assert segments[0].start == 0.0
