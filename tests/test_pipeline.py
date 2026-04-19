from pathlib import Path
from unittest.mock import MagicMock

import pytest

from whotalksitron.config import Config
from whotalksitron.models import SpeakerPool, TranscriptResult, TranscriptSegment
from whotalksitron.pipeline import (
    Pipeline,
    ValidationError,
    check_ffmpeg,
    validate_audio,
)


@pytest.fixture
def fake_audio(tmp_path) -> Path:
    audio = tmp_path / "test.mp3"
    audio.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 1000)
    return audio


def test_validate_audio_exists(fake_audio):
    info = validate_audio(fake_audio)
    assert info["path"] == fake_audio
    assert info["size_bytes"] > 0


def test_validate_audio_missing():
    with pytest.raises(ValidationError, match="not found"):
        validate_audio(Path("/nonexistent/file.mp3"))


def test_validate_audio_empty(tmp_path):
    empty = tmp_path / "empty.mp3"
    empty.write_bytes(b"")
    with pytest.raises(ValidationError, match="empty"):
        validate_audio(empty)


def test_check_ffmpeg_available():
    result = check_ffmpeg()
    assert isinstance(result, bool)


def test_pipeline_init():
    cfg = Config()
    cfg.gemini_api_key = "test"
    pipeline = Pipeline(cfg)
    assert pipeline is not None


def test_pipeline_run_with_mock_backend(fake_audio, tmp_path):
    cfg = Config()
    cfg.gemini_api_key = "test"

    mock_backend = MagicMock()
    mock_backend.name = "mock"
    mock_backend.supports_diarization.return_value = True
    mock_backend.is_available.return_value = True
    mock_backend.transcribe.return_value = TranscriptResult(
        segments=[
            TranscriptSegment(start=0.0, end=5.0, text="Hello.", speaker="Matt"),
            TranscriptSegment(start=5.0, end=10.0, text="World.", speaker="Speaker 1"),
        ],
        metadata={"model": "test", "backend": "mock"},
    )

    output_path = tmp_path / "output.md"

    pipeline = Pipeline(cfg)
    result = pipeline.run(
        audio_path=fake_audio,
        output_path=output_path,
        backend=mock_backend,
        podcast=None,
        speakers=None,
    )

    assert result.exit_code == 0
    assert output_path.exists()
    content = output_path.read_text()
    assert "Hello." in content
    assert "Matt" in content


def test_pipeline_result_partial_success(fake_audio, tmp_path):
    cfg = Config()

    mock_backend = MagicMock()
    mock_backend.name = "mock"
    mock_backend.supports_diarization.return_value = True
    mock_backend.is_available.return_value = True
    mock_backend.transcribe.return_value = TranscriptResult(
        segments=[
            TranscriptSegment(start=0.0, end=5.0, text="Hello."),
        ],
        metadata={"model": "test", "backend": "mock"},
    )

    output_path = tmp_path / "output.md"
    pipeline = Pipeline(cfg)

    pipeline.run(
        audio_path=fake_audio,
        output_path=output_path,
        backend=mock_backend,
        podcast="atp",
        speakers=SpeakerPool(podcast="atp", speakers={"matt": []}),
    )

    assert output_path.exists()
