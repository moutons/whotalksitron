# Phase 3: Backend System

Backend protocol, Gemini implementation, and Whisper-only implementation. After this phase, two backends produce real transcripts.

---

### Task 6: Backend protocol and auto-selection `[sonnet]`

**Files:**
- Create: `src/whotalksitron/backends/__init__.py`
- Create: `tests/test_backends/__init__.py`
- Create: `tests/test_backends/test_selection.py`

- [ ] **Step 1: Write failing tests for auto-selection**

Create `tests/test_backends/__init__.py` (empty file).

Create `tests/test_backends/test_selection.py`:

```python
import pytest

from whotalksitron.backends import (
    Backend,
    BackendUnavailableError,
    select_backend,
)
from whotalksitron.config import Config
from whotalksitron.models import SpeakerPool, TranscriptResult, TranscriptSegment
from whotalksitron.progress import ProgressCallback


class FakeBackend:
    name = "fake"

    def __init__(self, available: bool = True, diarization: bool = True):
        self._available = available
        self._diarization = diarization

    def transcribe(
        self,
        audio_path,
        *,
        speakers=None,
        progress=None,
    ) -> TranscriptResult:
        return TranscriptResult(segments=[], metadata={})

    def supports_diarization(self) -> bool:
        return self._diarization

    def is_available(self) -> bool:
        return self._available


def test_backend_protocol_compliance():
    backend: Backend = FakeBackend()
    assert backend.name == "fake"
    assert backend.is_available()
    assert backend.supports_diarization()
    result = backend.transcribe(
        "/fake/path.mp3",
        speakers=None,
        progress=None,
    )
    assert isinstance(result, TranscriptResult)


def test_select_backend_explicit(monkeypatch):
    cfg = Config()
    cfg.backend = "whisper"
    cfg.whisper_endpoint = "http://localhost:9999/v1"

    # Should attempt whisper even if unavailable — and raise
    with pytest.raises(BackendUnavailableError, match="whisper"):
        select_backend(cfg)


def test_select_backend_auto_no_backends(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    cfg = Config()
    cfg.backend = "auto"
    cfg.gemini_api_key = ""
    cfg.gemini_use_adc = False

    with pytest.raises(BackendUnavailableError, match="No backend available"):
        select_backend(cfg)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_backends/test_selection.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement backend protocol and selection**

Create `src/whotalksitron/backends/__init__.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from whotalksitron.config import Config
from whotalksitron.models import SpeakerPool, TranscriptResult
from whotalksitron.progress import ProgressCallback


class BackendUnavailableError(Exception):
    pass


@runtime_checkable
class Backend(Protocol):
    name: str

    def transcribe(
        self,
        audio_path: str | Path,
        *,
        speakers: SpeakerPool | None,
        progress: ProgressCallback | None,
    ) -> TranscriptResult: ...

    def supports_diarization(self) -> bool: ...

    def is_available(self) -> bool: ...


def select_backend(config: Config) -> Backend:
    if config.backend != "auto":
        backend = _create_backend(config.backend, config)
        if not backend.is_available():
            msg = _unavailable_message(config.backend, backend)
            raise BackendUnavailableError(msg)
        return backend

    for name in ("gemini", "pyannote", "whisper"):
        try:
            backend = _create_backend(name, config)
            if backend.is_available():
                return backend
        except BackendUnavailableError:
            continue

    raise BackendUnavailableError(
        "No backend available. Configure one of:\n"
        "  gemini:   set GEMINI_API_KEY or run `gcloud auth application-default login`\n"
        "  pyannote: install local extras with `uv tool install whotalksitron --with local`\n"
        "  whisper:  start Ollama or LM Studio at http://localhost:1234/v1"
    )


def _create_backend(name: str, config: Config) -> Backend:
    if name == "gemini":
        from whotalksitron.backends.gemini import GeminiBackend
        return GeminiBackend(config)
    elif name == "pyannote":
        from whotalksitron.backends.pyannote import PyAnnoteBackend
        return PyAnnoteBackend(config)
    elif name == "whisper":
        from whotalksitron.backends.whisper import WhisperBackend
        return WhisperBackend(config)
    else:
        raise BackendUnavailableError(f"Unknown backend: {name!r}")


def _unavailable_message(name: str, backend: Backend) -> str:
    hints = {
        "gemini": "Set GEMINI_API_KEY or run `gcloud auth application-default login`",
        "pyannote": "Install local extras: `uv tool install whotalksitron --with local`",
        "whisper": f"Start Ollama or LM Studio. No response from endpoint.",
    }
    hint = hints.get(name, "Check configuration.")
    return f"Backend {name!r} is not available. {hint}"
```

- [ ] **Step 4: Create stub backend files so imports don't crash**

Create `src/whotalksitron/backends/gemini.py`:

```python
from __future__ import annotations

from pathlib import Path

from whotalksitron.config import Config
from whotalksitron.models import SpeakerPool, TranscriptResult
from whotalksitron.progress import ProgressCallback


class GeminiBackend:
    name = "gemini"

    def __init__(self, config: Config) -> None:
        self._config = config

    def transcribe(
        self,
        audio_path: str | Path,
        *,
        speakers: SpeakerPool | None = None,
        progress: ProgressCallback | None = None,
    ) -> TranscriptResult:
        raise NotImplementedError

    def supports_diarization(self) -> bool:
        return True

    def is_available(self) -> bool:
        return bool(self._config.gemini_api_key or self._config.gemini_use_adc)
```

Create `src/whotalksitron/backends/whisper.py`:

```python
from __future__ import annotations

from pathlib import Path

import httpx

from whotalksitron.config import Config
from whotalksitron.models import SpeakerPool, TranscriptResult
from whotalksitron.progress import ProgressCallback


class WhisperBackend:
    name = "whisper"

    def __init__(self, config: Config) -> None:
        self._config = config

    def transcribe(
        self,
        audio_path: str | Path,
        *,
        speakers: SpeakerPool | None = None,
        progress: ProgressCallback | None = None,
    ) -> TranscriptResult:
        raise NotImplementedError

    def supports_diarization(self) -> bool:
        return False

    def is_available(self) -> bool:
        try:
            resp = httpx.get(
                f"{self._config.whisper_endpoint}/models",
                timeout=2.0,
            )
            return resp.status_code == 200
        except httpx.ConnectError:
            return False
```

Create `src/whotalksitron/backends/pyannote.py`:

```python
from __future__ import annotations

from pathlib import Path

from whotalksitron.config import Config
from whotalksitron.models import SpeakerPool, TranscriptResult
from whotalksitron.progress import ProgressCallback


class PyAnnoteBackend:
    name = "pyannote"

    def __init__(self, config: Config) -> None:
        self._config = config

    def transcribe(
        self,
        audio_path: str | Path,
        *,
        speakers: SpeakerPool | None = None,
        progress: ProgressCallback | None = None,
    ) -> TranscriptResult:
        raise NotImplementedError

    def supports_diarization(self) -> bool:
        return True

    def is_available(self) -> bool:
        try:
            import pyannote.audio  # noqa: F401
            import torch  # noqa: F401
            return True
        except ImportError:
            return False
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_backends/test_selection.py -v`
Expected: all 3 tests PASS

- [ ] **Step 6: Commit** `[COMMIT]`

```bash
git add src/whotalksitron/backends/ tests/test_backends/
git commit -m "Add backend protocol and auto-selection

Backend Protocol with select_backend() that tries gemini > pyannote
> whisper in order. Stub implementations for all three backends."
```

---

### Task 7: Gemini backend `[sonnet]`

**Files:**
- Modify: `src/whotalksitron/backends/gemini.py`
- Create: `tests/test_backends/test_gemini.py`

**Reference:** Read `docs/superpowers/specs/2026-04-18-whotalksitron-design/backends.md` for Gemini-specific behavior (voice samples as prompt context, File API for >20MB, speaker-attributed segments).

- [ ] **Step 1: Write failing tests**

Create `tests/test_backends/test_gemini.py`:

```python
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

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


def test_parse_response_hour_timestamps():
    response_text = "[01:23:45] Speaker 1: Long episode.\n"
    segments = _parse_response(response_text)
    assert segments[0].start == 5025.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_backends/test_gemini.py -v`
Expected: FAIL with `ImportError` for `_build_prompt`, `_parse_response`

- [ ] **Step 3: Implement Gemini backend**

Replace `src/whotalksitron/backends/gemini.py`:

```python
from __future__ import annotations

import logging
import re
from pathlib import Path

from google import genai
from google.genai import types

from whotalksitron.config import Config
from whotalksitron.models import SpeakerPool, TranscriptResult, TranscriptSegment
from whotalksitron.progress import ProgressCallback

logger = logging.getLogger(__name__)

_INLINE_SIZE_LIMIT = 20 * 1024 * 1024  # 20MB


class GeminiBackend:
    name = "gemini"

    def __init__(self, config: Config) -> None:
        self._config = config

    def transcribe(
        self,
        audio_path: str | Path,
        *,
        speakers: SpeakerPool | None = None,
        progress: ProgressCallback | None = None,
    ) -> TranscriptResult:
        audio_path = Path(audio_path)
        client = self._make_client()

        if progress:
            progress.update("transcribe", 0, "preparing Gemini request")

        contents = self._build_contents(audio_path, speakers, client)
        prompt = _build_prompt(speakers)

        if progress:
            progress.update("transcribe", 30, "sending to Gemini API")

        logger.debug("Gemini model: %s", self._config.gemini_model)
        response = client.models.generate_content(
            model=self._config.gemini_model,
            contents=[*contents, prompt],
        )

        if progress:
            progress.update("transcribe", 90, "parsing response")

        response_text = response.text or ""
        logger.debug("Gemini response length: %d chars", len(response_text))

        segments = _parse_response(response_text)

        token_count = None
        if response.usage_metadata:
            token_count = response.usage_metadata.total_token_count

        if progress:
            progress.stage_complete("transcribe", f"{len(segments)} segments")

        return TranscriptResult(
            segments=segments,
            metadata={
                "model": self._config.gemini_model,
                "backend": "gemini",
                "token_count": token_count,
            },
        )

    def supports_diarization(self) -> bool:
        return True

    def is_available(self) -> bool:
        return bool(self._config.gemini_api_key or self._config.gemini_use_adc)

    def _make_client(self) -> genai.Client:
        if self._config.gemini_api_key:
            return genai.Client(api_key=self._config.gemini_api_key)
        return genai.Client()

    def _build_contents(
        self,
        audio_path: Path,
        speakers: SpeakerPool | None,
        client: genai.Client,
    ) -> list[types.Part]:
        parts: list[types.Part] = []

        if speakers:
            for name, sample_paths in speakers.speakers.items():
                for sample_path in sample_paths:
                    part = self._upload_or_inline(sample_path, client)
                    parts.append(part)

        parts.append(self._upload_or_inline(audio_path, client))
        return parts

    def _upload_or_inline(
        self, path: Path, client: genai.Client
    ) -> types.Part:
        file_size = path.stat().st_size
        mime = _guess_mime(path)

        if file_size > _INLINE_SIZE_LIMIT:
            logger.info("Uploading %s via File API (%d bytes)", path.name, file_size)
            uploaded = client.files.upload(file=path)
            return types.Part.from_uri(file_uri=uploaded.uri, mime_type=mime)

        logger.debug("Inlining %s (%d bytes)", path.name, file_size)
        data = path.read_bytes()
        return types.Part.from_bytes(data=data, mime_type=mime)


def _build_prompt(speakers: SpeakerPool | None) -> str:
    base = (
        "Transcribe this audio with speaker diarization. "
        "Format each line as: [HH:MM:SS] Speaker Name: text\n"
        "Use consistent speaker names throughout. "
        "If you cannot identify a speaker, use 'Speaker 1', 'Speaker 2', etc."
    )
    if speakers and speakers.speakers:
        names = ", ".join(sorted(speakers.speakers.keys()))
        base += (
            f"\n\nI have provided voice samples for known speakers: {names}. "
            "The audio samples before the main recording are voice references. "
            "Match speakers in the recording against these references and use "
            "their names. For any speakers that don't match a reference, use "
            "'Speaker 1', 'Speaker 2', etc."
        )
    return base


def _parse_response(text: str) -> list[TranscriptSegment]:
    pattern = re.compile(
        r"\[(\d{1,2}:\d{2}:\d{2})\]\s*"
        r"(?:([^:]+?):\s*)?"
        r"(.+)"
    )
    segments: list[TranscriptSegment] = []

    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        match = pattern.match(line)
        if not match:
            logger.debug("Skipping unparseable line: %s", line)
            continue

        timestamp_str, speaker, content = match.groups()
        seconds = _parse_timestamp(timestamp_str)
        speaker = speaker.strip() if speaker else None

        segments.append(TranscriptSegment(
            start=seconds,
            end=seconds,  # end set below
            text=content.strip(),
            speaker=speaker,
        ))

    # Set end times: each segment ends when the next one starts
    for i in range(len(segments) - 1):
        segments[i] = TranscriptSegment(
            start=segments[i].start,
            end=segments[i + 1].start,
            text=segments[i].text,
            speaker=segments[i].speaker,
        )
    # Last segment: assume 30 seconds if no next segment
    if segments:
        last = segments[-1]
        segments[-1] = TranscriptSegment(
            start=last.start,
            end=last.start + 30.0,
            text=last.text,
            speaker=last.speaker,
        )

    return segments


def _parse_timestamp(ts: str) -> float:
    parts = ts.split(":")
    h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
    return h * 3600.0 + m * 60.0 + s


def _guess_mime(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".flac": "audio/flac",
        ".ogg": "audio/ogg",
        ".m4a": "audio/mp4",
        ".webm": "audio/webm",
    }.get(suffix, "audio/mpeg")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_backends/test_gemini.py -v`
Expected: all 8 tests PASS

- [ ] **Step 5: Commit** `[COMMIT]`

```bash
git add src/whotalksitron/backends/gemini.py tests/test_backends/test_gemini.py
git commit -m "Implement Gemini backend

Sends audio + optional voice samples to Gemini API. Parses
timestamped speaker-attributed response. Handles File API
upload for files >20MB."
```

`[REVIEW:normal]` — First working backend. Check protocol compliance, prompt design, response parsing.

---

### Task 8: Whisper-only backend `[sonnet]`

**Files:**
- Modify: `src/whotalksitron/backends/whisper.py`
- Create: `tests/test_backends/test_whisper.py`

**Reference:** Read `docs/superpowers/specs/2026-04-18-whotalksitron-design/backends.md` for Whisper-only behavior (OpenAI-compatible endpoint, no diarization, httpx client).

- [ ] **Step 1: Write failing tests**

Create `tests/test_backends/test_whisper.py`:

```python
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_backends/test_whisper.py -v`
Expected: FAIL with `ImportError` for `_parse_whisper_response`

- [ ] **Step 3: Implement Whisper backend**

Replace `src/whotalksitron/backends/whisper.py`:

```python
from __future__ import annotations

import logging
from pathlib import Path

import httpx

from whotalksitron.config import Config
from whotalksitron.models import SpeakerPool, TranscriptResult, TranscriptSegment
from whotalksitron.progress import ProgressCallback

logger = logging.getLogger(__name__)


class WhisperBackend:
    name = "whisper"

    def __init__(self, config: Config) -> None:
        self._config = config

    def transcribe(
        self,
        audio_path: str | Path,
        *,
        speakers: SpeakerPool | None = None,
        progress: ProgressCallback | None = None,
    ) -> TranscriptResult:
        audio_path = Path(audio_path)

        if progress:
            progress.update("transcribe", 0, "sending to Whisper endpoint")

        url = f"{self._config.whisper_endpoint}/audio/transcriptions"
        logger.debug("Whisper endpoint: %s", url)
        logger.debug("Whisper model: %s", self._config.whisper_model)

        with open(audio_path, "rb") as f:
            response = httpx.post(
                url,
                files={"file": (audio_path.name, f, "audio/mpeg")},
                data={
                    "model": self._config.whisper_model,
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": "segment",
                },
                timeout=600.0,
            )

        if progress:
            progress.update("transcribe", 80, "parsing response")

        response.raise_for_status()
        data = response.json()

        segments = _parse_whisper_response(data)

        if progress:
            progress.stage_complete("transcribe", f"{len(segments)} segments")

        return TranscriptResult(
            segments=segments,
            metadata={
                "model": self._config.whisper_model,
                "backend": "whisper",
                "endpoint": self._config.whisper_endpoint,
            },
        )

    def supports_diarization(self) -> bool:
        return False

    def is_available(self) -> bool:
        try:
            resp = httpx.get(
                f"{self._config.whisper_endpoint}/models",
                timeout=2.0,
            )
            return resp.status_code == 200
        except httpx.ConnectError:
            return False


def _parse_whisper_response(data: dict) -> list[TranscriptSegment]:
    raw_segments = data.get("segments")

    if raw_segments is None:
        text = data.get("text", "").strip()
        if not text:
            return []
        return [TranscriptSegment(start=0.0, end=0.0, text=text)]

    segments: list[TranscriptSegment] = []
    for seg in raw_segments:
        text = seg.get("text", "").strip()
        if not text:
            continue
        segments.append(TranscriptSegment(
            start=float(seg.get("start", 0.0)),
            end=float(seg.get("end", 0.0)),
            text=text,
        ))
    return segments
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_backends/test_whisper.py -v`
Expected: all 4 tests PASS

- [ ] **Step 5: Run full suite and commit** `[COMMIT]`

Run: `just test`
Expected: all tests pass

```bash
git add src/whotalksitron/backends/whisper.py tests/test_backends/test_whisper.py
git commit -m "Implement Whisper-only backend

Calls OpenAI-compatible /v1/audio/transcriptions endpoint via httpx.
Returns segments without speaker attribution. Parses both verbose_json
and plain text response formats."
```

Push and `[REVIEW:light]` — Phase 3 complete. Two backends implemented.
