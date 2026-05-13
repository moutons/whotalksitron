from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from whotalksitron.config import Config


def _make_config(**overrides) -> Config:
    cfg = Config()
    cfg.mistral_endpoint = "https://api.mistral.ai/v1"
    cfg.mistral_model = "voxtral-mini-latest"
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def test_backend_is_available_when_key_set():
    from whotalksitron.backends.mistral import MistralBackend
    backend = MistralBackend(_make_config(mistral_api_key="sk-test"))
    assert backend.is_available() is True


def test_backend_is_available_false_when_key_missing():
    from whotalksitron.backends.mistral import MistralBackend
    backend = MistralBackend(_make_config())
    assert backend.is_available() is False


def test_backend_name_and_diarization():
    from whotalksitron.backends.mistral import MistralBackend
    backend = MistralBackend(_make_config(mistral_api_key="sk-test"))
    assert backend.name == "mistral"
    assert backend.supports_diarization() is False


_HAPPY_RESPONSE = {
    "model": "voxtral-mini-2507",
    "text": "Hello world. Goodbye.",
    "language": "en",
    "segments": [
        {"start": 0.0, "end": 1.2, "text": "Hello world."},
        {"start": 1.2, "end": 2.4, "text": "Goodbye."},
    ],
    "usage": {
        "prompt_audio_seconds": 3,
        "prompt_tokens": 4,
        "completion_tokens": 5,
        "total_tokens": 9,
    },
}


def _mock_response(status_code: int = 200, body: dict | None = None,
                   text: str = "", headers: dict | None = None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.text = text or json.dumps(body or {})
    resp.json.return_value = body if body is not None else {}
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"{status_code} error", request=MagicMock(), response=resp
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


def test_transcribe_zero_byte_audio_raises(tmp_path):
    from whotalksitron.backends.mistral import MistralBackend
    audio = tmp_path / "empty.mp3"
    audio.write_bytes(b"")
    backend = MistralBackend(_make_config(mistral_api_key="sk-test"))
    with pytest.raises(ValueError, match="empty"):
        backend.transcribe(audio)


def test_transcribe_happy_path_request_shape(tmp_path):
    from whotalksitron.backends.mistral import MistralBackend
    audio = tmp_path / "clip.mp3"
    audio.write_bytes(b"fake-audio-bytes")
    backend = MistralBackend(_make_config(mistral_api_key="sk-test"))

    with patch(
        "whotalksitron.backends.mistral.httpx.post",
        return_value=_mock_response(200, _HAPPY_RESPONSE),
    ) as post:
        result = backend.transcribe(audio)

    assert post.call_count == 1
    args, kwargs = post.call_args
    assert args[0] == "https://api.mistral.ai/v1/audio/transcriptions"
    assert kwargs["headers"] == {"Authorization": "Bearer sk-test"}
    assert kwargs["data"] == {
        "model": "voxtral-mini-latest",
        "timestamp_granularities": "segment",
    }
    assert "response_format" not in kwargs["data"]
    file_field = kwargs["files"]["file"]
    assert file_field[0] == "clip.mp3"
    assert file_field[1] == b"fake-audio-bytes"
    assert kwargs["timeout"] == 600.0
    assert len(result.segments) == 2
    assert result.segments[0].text == "Hello world."
    assert all(s.speaker is None for s in result.segments)
    assert result.metadata["backend"] == "mistral"
    assert result.metadata["model"] == "voxtral-mini-2507"
    assert result.metadata["token_count"] == 9
    assert result.metadata["prompt_audio_seconds"] == 3


def test_transcribe_strips_trailing_slash_in_url(tmp_path):
    from whotalksitron.backends.mistral import MistralBackend
    audio = tmp_path / "clip.mp3"
    audio.write_bytes(b"x")
    backend = MistralBackend(_make_config(
        mistral_api_key="sk-test",
        mistral_endpoint="https://api.mistral.ai/v1",
    ))
    with patch(
        "whotalksitron.backends.mistral.httpx.post",
        return_value=_mock_response(200, _HAPPY_RESPONSE),
    ) as post:
        backend.transcribe(audio)
    assert post.call_args[0][0] == "https://api.mistral.ai/v1/audio/transcriptions"
    assert "//audio" not in post.call_args[0][0]


def test_transcribe_empty_segments_fallback(tmp_path, caplog):
    from whotalksitron.backends.mistral import MistralBackend
    audio = tmp_path / "clip.mp3"
    audio.write_bytes(b"x")
    backend = MistralBackend(_make_config(mistral_api_key="sk-test"))
    body = {"model": "voxtral-mini-2507", "text": "Single chunk.", "segments": []}
    with patch(
        "whotalksitron.backends.mistral.httpx.post",
        return_value=_mock_response(200, body),
    ), caplog.at_level("INFO", logger="whotalksitron.backends.mistral"):
        result = backend.transcribe(audio)
    assert len(result.segments) == 1
    assert result.segments[0].text == "Single chunk."
    assert result.segments[0].start == 0.0
    assert result.segments[0].end == 0.0
    assert any("no segment timestamps" in r.message.lower() for r in caplog.records)


def test_transcribe_missing_start_end_defaults_to_zero(tmp_path):
    from whotalksitron.backends.mistral import MistralBackend
    audio = tmp_path / "clip.mp3"
    audio.write_bytes(b"x")
    backend = MistralBackend(_make_config(mistral_api_key="sk-test"))
    body = {"text": "x", "segments": [{"text": "no times"}]}
    with patch(
        "whotalksitron.backends.mistral.httpx.post",
        return_value=_mock_response(200, body),
    ):
        result = backend.transcribe(audio)
    assert result.segments[0].start == 0.0
    assert result.segments[0].end == 0.0
    assert result.segments[0].text == "no times"


def test_transcribe_inverted_segment_warns_but_keeps(tmp_path, caplog):
    from whotalksitron.backends.mistral import MistralBackend
    audio = tmp_path / "clip.mp3"
    audio.write_bytes(b"x")
    backend = MistralBackend(_make_config(mistral_api_key="sk-test"))
    body = {"segments": [{"start": 5.0, "end": 2.0, "text": "bad"}]}
    with patch(
        "whotalksitron.backends.mistral.httpx.post",
        return_value=_mock_response(200, body),
    ), caplog.at_level("WARNING", logger="whotalksitron.backends.mistral"):
        result = backend.transcribe(audio)
    assert len(result.segments) == 1
    assert any("start" in r.message.lower() and "end" in r.message.lower()
               for r in caplog.records)


def test_transcribe_non_json_response_raises_runtime_error(tmp_path):
    from whotalksitron.backends.mistral import MistralBackend
    audio = tmp_path / "clip.mp3"
    audio.write_bytes(b"x")
    backend = MistralBackend(_make_config(mistral_api_key="sk-test"))
    resp = _mock_response(200, body=None, text="<html>502 Bad Gateway</html>")
    resp.json.side_effect = json.JSONDecodeError("bad", "doc", 0)
    with (
        patch("whotalksitron.backends.mistral.httpx.post", return_value=resp),
        pytest.raises(RuntimeError, match="parse"),
    ):
        backend.transcribe(audio)


def test_transcribe_413_friendly_error_no_retry(tmp_path):
    from whotalksitron.backends.mistral import MistralBackend
    audio = tmp_path / "clip.mp3"
    audio.write_bytes(b"x")
    backend = MistralBackend(_make_config(mistral_api_key="sk-test"))
    with (
        patch(
            "whotalksitron.backends.mistral.httpx.post",
            return_value=_mock_response(413, body={"error": "too large"}),
        ) as post,
        pytest.raises(RuntimeError, match="3 hours"),
    ):
        backend.transcribe(audio)
    assert post.call_count == 1


def test_transcribe_401_no_retry(tmp_path):
    from whotalksitron.backends.mistral import MistralBackend
    audio = tmp_path / "clip.mp3"
    audio.write_bytes(b"x")
    backend = MistralBackend(_make_config(mistral_api_key="sk-bad"))
    with (
        patch(
            "whotalksitron.backends.mistral.httpx.post",
            return_value=_mock_response(401, body={"error": "unauthorized"}),
        ) as post,
        pytest.raises(RuntimeError),
    ):
        backend.transcribe(audio)
    assert post.call_count == 1


def test_transcribe_429_retries_then_fails(tmp_path):
    from whotalksitron.backends.mistral import MistralBackend
    audio = tmp_path / "clip.mp3"
    audio.write_bytes(b"x")
    backend = MistralBackend(_make_config(mistral_api_key="sk-test"))
    with (
        patch(
            "whotalksitron.backends.mistral.httpx.post",
            return_value=_mock_response(
                429, body={"error": "rate limited"}, headers={"Retry-After": "1"}
            ),
        ) as post,
        patch("whotalksitron.retry.time.sleep"),
        pytest.raises(RuntimeError, match="3 retries"),
    ):
        backend.transcribe(audio)
    assert post.call_count == 4  # initial + 3 retries


def test_transcribe_500_retries_then_recovers(tmp_path):
    from whotalksitron.backends.mistral import MistralBackend
    audio = tmp_path / "clip.mp3"
    audio.write_bytes(b"x")
    backend = MistralBackend(_make_config(mistral_api_key="sk-test"))
    responses = [
        _mock_response(500, body={"error": "boom"}),
        _mock_response(200, _HAPPY_RESPONSE),
    ]
    with patch(
        "whotalksitron.backends.mistral.httpx.post",
        side_effect=responses,
    ), patch("whotalksitron.retry.time.sleep"):
        result = backend.transcribe(audio)
    assert len(result.segments) == 2
