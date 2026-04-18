# Phase 2: Core Foundation

Core types, configuration, progress reporting, and markdown output. After this phase, the data model is locked in and the output formatter produces valid transcripts from test data.

---

### Task 2: Core models `[sonnet]`

**Files:**
- Create: `src/whotalksitron/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing tests for core data types**

Create `tests/test_models.py`:

```python
from pathlib import Path

from whotalksitron.models import SpeakerPool, TranscriptResult, TranscriptSegment


def test_segment_creation():
    seg = TranscriptSegment(start=0.0, end=5.5, text="Hello world", speaker="Matt")
    assert seg.start == 0.0
    assert seg.end == 5.5
    assert seg.text == "Hello world"
    assert seg.speaker == "Matt"


def test_segment_speaker_none():
    seg = TranscriptSegment(start=0.0, end=1.0, text="test")
    assert seg.speaker is None


def test_segment_duration():
    seg = TranscriptSegment(start=10.0, end=25.5, text="test")
    assert seg.duration == 15.5


def test_segment_timestamp_str():
    seg = TranscriptSegment(start=3661.5, end=3670.0, text="test")
    assert seg.start_timestamp == "01:01:01"
    assert seg.end_timestamp == "01:01:10"


def test_result_creation():
    segments = [
        TranscriptSegment(start=0.0, end=5.0, text="Hello", speaker="Matt"),
        TranscriptSegment(start=5.0, end=10.0, text="Hi", speaker=None),
    ]
    result = TranscriptResult(segments=segments, metadata={"model": "test"})
    assert len(result.segments) == 2
    assert result.metadata["model"] == "test"


def test_result_duration():
    segments = [
        TranscriptSegment(start=0.0, end=5.0, text="a"),
        TranscriptSegment(start=5.0, end=90.0, text="b"),
    ]
    result = TranscriptResult(segments=segments, metadata={})
    assert result.duration == 90.0


def test_result_speakers():
    segments = [
        TranscriptSegment(start=0.0, end=5.0, text="a", speaker="Matt"),
        TranscriptSegment(start=5.0, end=10.0, text="b", speaker=None),
        TranscriptSegment(start=10.0, end=15.0, text="c", speaker="Matt"),
        TranscriptSegment(start=15.0, end=20.0, text="d", speaker="Speaker 2"),
    ]
    result = TranscriptResult(segments=segments, metadata={})
    assert result.speakers == {"Matt", "Speaker 2"}
    assert result.unmatched_speakers == {"Speaker 2"}


def test_speaker_pool_empty():
    pool = SpeakerPool(podcast="atp", speakers={})
    assert pool.podcast == "atp"
    assert len(pool.speakers) == 0


def test_speaker_pool_with_speakers():
    pool = SpeakerPool(
        podcast="atp",
        speakers={
            "matt": [Path("/samples/matt1.wav"), Path("/samples/matt2.wav")],
        },
    )
    assert "matt" in pool.speakers
    assert len(pool.speakers["matt"]) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError` or `ImportError`

- [ ] **Step 3: Implement core models**

Create `src/whotalksitron/models.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str
    speaker: str | None = None

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def start_timestamp(self) -> str:
        return _format_timestamp(self.start)

    @property
    def end_timestamp(self) -> str:
        return _format_timestamp(self.end)


@dataclass
class TranscriptResult:
    segments: list[TranscriptSegment]
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        if not self.segments:
            return 0.0
        return self.segments[-1].end

    @property
    def speakers(self) -> set[str]:
        return {s.speaker for s in self.segments if s.speaker is not None}

    @property
    def unmatched_speakers(self) -> set[str]:
        pattern = re.compile(r"^Speaker \d+$")
        return {s for s in self.speakers if pattern.match(s)}


@dataclass
class SpeakerPool:
    podcast: str
    speakers: dict[str, list[Path]] = field(default_factory=dict)


def _format_timestamp(seconds: float) -> str:
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_models.py -v`
Expected: all 10 tests PASS

- [ ] **Step 5: Commit** `[COMMIT]`

```bash
git add src/whotalksitron/models.py tests/test_models.py
git commit -m "Add core data models

TranscriptSegment, TranscriptResult, and SpeakerPool dataclasses
with timestamp formatting, duration, and speaker tracking."
```

---

### Task 3: Configuration system `[sonnet]`

**Files:**
- Create: `src/whotalksitron/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing tests for config**

Create `tests/test_config.py`:

```python
import os
from pathlib import Path

import tomli_w

from whotalksitron.config import Config, load_config


def test_default_config():
    cfg = Config()
    assert cfg.backend == "auto"
    assert cfg.log_level == "info"
    assert cfg.progress is False
    assert cfg.gemini_model == "gemini-2.5-flash"
    assert cfg.pyannote_whisper_model == "large-v3"
    assert cfg.pyannote_device == "auto"
    assert cfg.whisper_endpoint == "http://localhost:1234/v1"
    assert cfg.match_threshold == 0.7
    assert cfg.timestamp_format == "HH:MM:SS"


def test_config_from_dict():
    cfg = Config.from_dict({
        "defaults": {"backend": "gemini", "log_level": "debug"},
        "gemini": {"model": "gemini-2.5-pro"},
        "speakers": {"match_threshold": 0.85},
    })
    assert cfg.backend == "gemini"
    assert cfg.log_level == "debug"
    assert cfg.gemini_model == "gemini-2.5-pro"
    assert cfg.match_threshold == 0.85
    assert cfg.progress is False


def test_config_from_toml_file(tmp_path):
    config_file = tmp_path / "config.toml"
    data = {
        "defaults": {"backend": "pyannote", "progress": True},
        "gemini": {"api_key": "test-key-123"},
    }
    config_file.write_bytes(tomli_w.dumps(data).encode())

    cfg = Config.from_file(config_file)
    assert cfg.backend == "pyannote"
    assert cfg.progress is True
    assert cfg.gemini_api_key == "test-key-123"


def test_config_missing_file_returns_defaults():
    cfg = Config.from_file(Path("/nonexistent/config.toml"))
    assert cfg.backend == "auto"


def test_config_env_override(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "env-key-456")
    monkeypatch.setenv("WHOTALKSITRON_BACKEND", "whisper")
    monkeypatch.setenv("WHOTALKSITRON_LOG_LEVEL", "error")

    cfg = load_config(config_path=None, cli_overrides={})
    assert cfg.gemini_api_key == "env-key-456"
    assert cfg.backend == "whisper"
    assert cfg.log_level == "error"


def test_config_cli_overrides_beat_env(monkeypatch):
    monkeypatch.setenv("WHOTALKSITRON_BACKEND", "whisper")
    cfg = load_config(
        config_path=None,
        cli_overrides={"backend": "gemini"},
    )
    assert cfg.backend == "gemini"


def test_config_full_precedence(tmp_path, monkeypatch):
    config_file = tmp_path / "config.toml"
    data = {"defaults": {"backend": "pyannote", "log_level": "warn"}}
    config_file.write_bytes(tomli_w.dumps(data).encode())

    monkeypatch.setenv("WHOTALKSITRON_BACKEND", "whisper")

    cfg = load_config(
        config_path=config_file,
        cli_overrides={"backend": "gemini"},
    )
    assert cfg.backend == "gemini"  # CLI wins


def test_config_show_masks_secrets():
    cfg = Config()
    cfg.gemini_api_key = "AIzaSyD-abc123-very-secret-key"
    shown = cfg.show()
    assert "AIzaSyD-abc123-very-secret-key" not in shown
    assert "AIza...key" in shown or "****" in shown


def test_config_dir():
    cfg = Config()
    assert cfg.config_dir == Path.home() / ".config" / "whotalksitron"


def test_config_speakers_dir():
    cfg = Config()
    assert cfg.speakers_dir == cfg.config_dir / "speakers"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement config module**

Create `src/whotalksitron/config.py`:

```python
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import tomli_w


@dataclass
class Config:
    backend: str = "auto"
    log_level: str = "info"
    log_format: str = "text"
    progress: bool = False

    gemini_api_key: str = ""
    gemini_use_adc: bool = False
    gemini_model: str = "gemini-2.5-flash"

    pyannote_whisper_model: str = "large-v3"
    pyannote_diarization_model: str = "pyannote/speaker-diarization-3.1"
    pyannote_device: str = "auto"

    whisper_endpoint: str = "http://localhost:1234/v1"
    whisper_model: str = "whisper-large-v3"

    match_threshold: float = 0.7
    timestamp_format: str = "HH:MM:SS"

    @property
    def config_dir(self) -> Path:
        return Path.home() / ".config" / "whotalksitron"

    @property
    def speakers_dir(self) -> Path:
        return self.config_dir / "speakers"

    @property
    def staging_dir(self) -> Path:
        return self.config_dir / "staging"

    @classmethod
    def from_dict(cls, data: dict) -> Config:
        cfg = cls()
        defaults = data.get("defaults", {})
        gemini = data.get("gemini", {})
        pyannote = data.get("pyannote", {})
        whisper = data.get("whisper", {})
        speakers = data.get("speakers", {})
        output = data.get("output", {})

        if "backend" in defaults:
            cfg.backend = defaults["backend"]
        if "log_level" in defaults:
            cfg.log_level = defaults["log_level"]
        if "log_format" in defaults:
            cfg.log_format = defaults["log_format"]
        if "progress" in defaults:
            cfg.progress = defaults["progress"]

        if "api_key" in gemini:
            cfg.gemini_api_key = gemini["api_key"]
        if "use_adc" in gemini:
            cfg.gemini_use_adc = gemini["use_adc"]
        if "model" in gemini:
            cfg.gemini_model = gemini["model"]

        if "whisper_model" in pyannote:
            cfg.pyannote_whisper_model = pyannote["whisper_model"]
        if "diarization_model" in pyannote:
            cfg.pyannote_diarization_model = pyannote["diarization_model"]
        if "device" in pyannote:
            cfg.pyannote_device = pyannote["device"]

        if "endpoint" in whisper:
            cfg.whisper_endpoint = whisper["endpoint"]
        if "model" in whisper:
            cfg.whisper_model = whisper["model"]

        if "match_threshold" in speakers:
            cfg.match_threshold = speakers["match_threshold"]

        if "timestamp_format" in output:
            cfg.timestamp_format = output["timestamp_format"]

        return cfg

    @classmethod
    def from_file(cls, path: Path) -> Config:
        if not path.exists():
            return cls()
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return cls.from_dict(data)

    def show(self) -> str:
        lines = []
        lines.append(f"backend = {self.backend!r}")
        lines.append(f"log_level = {self.log_level!r}")
        lines.append(f"progress = {self.progress!r}")

        masked_key = _mask_secret(self.gemini_api_key)
        lines.append(f"gemini.api_key = {masked_key!r}")
        lines.append(f"gemini.use_adc = {self.gemini_use_adc!r}")
        lines.append(f"gemini.model = {self.gemini_model!r}")

        lines.append(f"pyannote.whisper_model = {self.pyannote_whisper_model!r}")
        lines.append(f"pyannote.device = {self.pyannote_device!r}")

        lines.append(f"whisper.endpoint = {self.whisper_endpoint!r}")
        lines.append(f"whisper.model = {self.whisper_model!r}")

        lines.append(f"speakers.match_threshold = {self.match_threshold!r}")
        return "\n".join(lines)

    def write_default(self, path: Path) -> None:
        data = {
            "defaults": {
                "backend": self.backend,
                "log_level": self.log_level,
                "progress": self.progress,
            },
            "gemini": {
                "api_key": "",
                "use_adc": False,
                "model": self.gemini_model,
            },
            "pyannote": {
                "whisper_model": self.pyannote_whisper_model,
                "diarization_model": self.pyannote_diarization_model,
                "device": self.pyannote_device,
            },
            "whisper": {
                "endpoint": self.whisper_endpoint,
                "model": self.whisper_model,
            },
            "speakers": {
                "match_threshold": self.match_threshold,
            },
            "output": {
                "timestamp_format": self.timestamp_format,
            },
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            tomli_w.dump(data, f)


def load_config(
    config_path: Path | None,
    cli_overrides: dict[str, object],
) -> Config:
    if config_path is None:
        config_path = Path.home() / ".config" / "whotalksitron" / "config.toml"

    cfg = Config.from_file(config_path)

    env_map = {
        "GEMINI_API_KEY": "gemini_api_key",
        "WHOTALKSITRON_BACKEND": "backend",
        "WHOTALKSITRON_LOG_LEVEL": "log_level",
    }
    for env_var, attr in env_map.items():
        val = os.environ.get(env_var)
        if val is not None:
            setattr(cfg, attr, val)

    for key, val in cli_overrides.items():
        if val is not None and hasattr(cfg, key):
            setattr(cfg, key, val)

    return cfg


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return value[:4] + "..." + value[-3:]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: all 10 tests PASS

- [ ] **Step 5: Commit** `[COMMIT]`

```bash
git add src/whotalksitron/config.py tests/test_config.py
git commit -m "Add configuration system

TOML config file, env var overrides, CLI flag precedence, secret
masking, and default config generation."
```

---

### Task 4: Progress reporting `[sonnet]`

**Files:**
- Create: `src/whotalksitron/progress.py`
- Create: `tests/test_progress.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_progress.py`:

```python
import json
import io

from whotalksitron.progress import ProgressReporter


def test_progress_emits_json_line():
    buf = io.StringIO()
    reporter = ProgressReporter(stream=buf, enabled=True)
    reporter.update("transcribe", 45, "processing chunk 3/7")

    line = buf.getvalue().strip()
    data = json.loads(line)
    assert data["stage"] == "transcribe"
    assert data["percent"] == 45
    assert data["detail"] == "processing chunk 3/7"


def test_progress_disabled_emits_nothing():
    buf = io.StringIO()
    reporter = ProgressReporter(stream=buf, enabled=False)
    reporter.update("transcribe", 100, "done")
    assert buf.getvalue() == ""


def test_progress_multiple_updates():
    buf = io.StringIO()
    reporter = ProgressReporter(stream=buf, enabled=True)
    reporter.update("validate", 100, "ok")
    reporter.update("preprocess", 50, "converting")

    lines = buf.getvalue().strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["stage"] == "validate"
    assert json.loads(lines[1])["stage"] == "preprocess"


def test_progress_stage_complete_helper():
    buf = io.StringIO()
    reporter = ProgressReporter(stream=buf, enabled=True)
    reporter.stage_complete("validate", "ep42.mp3, 01:23:45")

    data = json.loads(buf.getvalue().strip())
    assert data["percent"] == 100
    assert data["stage"] == "validate"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_progress.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement progress reporter**

Create `src/whotalksitron/progress.py`:

```python
from __future__ import annotations

import json
import sys
from typing import IO, Protocol


class ProgressCallback(Protocol):
    def update(self, stage: str, percent: int, detail: str) -> None: ...
    def stage_complete(self, stage: str, detail: str) -> None: ...


class ProgressReporter:
    def __init__(
        self,
        stream: IO[str] | None = None,
        enabled: bool = True,
    ) -> None:
        self._stream = stream or sys.stderr
        self._enabled = enabled

    def update(self, stage: str, percent: int, detail: str) -> None:
        if not self._enabled:
            return
        line = json.dumps(
            {"stage": stage, "percent": percent, "detail": detail},
            ensure_ascii=False,
        )
        self._stream.write(line + "\n")
        self._stream.flush()

    def stage_complete(self, stage: str, detail: str) -> None:
        self.update(stage, 100, detail)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_progress.py -v`
Expected: all 4 tests PASS

---

### Task 5: Markdown output formatter `[sonnet]`

**Files:**
- Create: `src/whotalksitron/output.py`
- Create: `tests/test_output.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_output.py`:

```python
from whotalksitron.models import TranscriptResult, TranscriptSegment
from whotalksitron.output import render_transcript


def test_render_basic_transcript():
    result = TranscriptResult(
        segments=[
            TranscriptSegment(start=0.0, end=5.0, text="Hello world.", speaker="Matt"),
            TranscriptSegment(start=5.0, end=10.0, text="Hi there.", speaker="Speaker 2"),
        ],
        metadata={"model": "gemini-2.5-flash", "backend": "gemini"},
    )
    output = render_transcript(
        result,
        source_file="episode.mp3",
        podcast="atp",
    )

    assert "# Transcript: episode.mp3" in output
    assert "**[00:00:00] Matt:** Hello world." in output
    assert "**[00:00:05] Speaker 2:** Hi there." in output


def test_render_includes_metadata_comment():
    result = TranscriptResult(
        segments=[
            TranscriptSegment(start=0.0, end=60.0, text="test"),
        ],
        metadata={"model": "gemini-2.5-flash", "backend": "gemini"},
    )
    output = render_transcript(result, source_file="ep.mp3", podcast="atp")
    assert "<!-- whotalksitron" in output
    assert "gemini-2.5-flash" in output
    assert "podcast:atp" in output


def test_render_no_podcast():
    result = TranscriptResult(
        segments=[
            TranscriptSegment(start=0.0, end=5.0, text="Hello."),
        ],
        metadata={"model": "test", "backend": "test"},
    )
    output = render_transcript(result, source_file="test.mp3")
    assert "podcast:" not in output


def test_render_speaker_none():
    result = TranscriptResult(
        segments=[
            TranscriptSegment(start=0.0, end=5.0, text="No speaker info."),
        ],
        metadata={"model": "test", "backend": "whisper"},
    )
    output = render_transcript(result, source_file="test.mp3")
    assert "**[00:00:00]** No speaker info." in output


def test_render_duration_format():
    result = TranscriptResult(
        segments=[
            TranscriptSegment(start=0.0, end=5025.0, text="long"),
        ],
        metadata={"model": "test", "backend": "test"},
    )
    output = render_transcript(result, source_file="long.mp3")
    assert "01:23:45" in output


def test_render_mixed_speakers():
    result = TranscriptResult(
        segments=[
            TranscriptSegment(start=0.0, end=5.0, text="Known.", speaker="Matt"),
            TranscriptSegment(start=5.0, end=10.0, text="Unknown.", speaker="Speaker 1"),
            TranscriptSegment(start=10.0, end=15.0, text="No label."),
        ],
        metadata={"model": "test", "backend": "test"},
    )
    output = render_transcript(result, source_file="test.mp3")
    assert "**[00:00:00] Matt:**" in output
    assert "**[00:00:05] Speaker 1:**" in output
    assert "**[00:00:10]**" in output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_output.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement output formatter**

Create `src/whotalksitron/output.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

from whotalksitron.models import TranscriptResult, _format_timestamp


def render_transcript(
    result: TranscriptResult,
    source_file: str,
    podcast: str | None = None,
) -> str:
    lines: list[str] = []

    lines.append(f"# Transcript: {source_file}")
    lines.append("")
    lines.append(_metadata_comment(result, podcast))
    lines.append("")

    for segment in result.segments:
        ts = segment.start_timestamp
        if segment.speaker:
            lines.append(f"**[{ts}] {segment.speaker}:** {segment.text}")
        else:
            lines.append(f"**[{ts}]** {segment.text}")
        lines.append("")

    return "\n".join(lines)


def _metadata_comment(result: TranscriptResult, podcast: str | None) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    model = result.metadata.get("model", "unknown")
    duration = _format_timestamp(result.duration)

    parts = ["whotalksitron", now, str(model), duration]
    if podcast:
        parts.append(f"podcast:{podcast}")

    return "<!-- " + " | ".join(parts) + " -->"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_output.py -v`
Expected: all 6 tests PASS

- [ ] **Step 5: Run full suite and commit** `[COMMIT]`

Run: `just test`
Expected: all tests pass (models + config + progress + output + cli)

Run: `just ensureci-sandbox`
Expected: all checks pass

```bash
git add src/whotalksitron/progress.py src/whotalksitron/output.py tests/test_progress.py tests/test_output.py
git commit -m "Add progress reporter and markdown output formatter

JSON progress lines on stderr for machine-parseable stage updates.
Markdown renderer produces inline speaker labels with timestamps."
```

`[REVIEW:light]` — Phase 2 complete. Verify core foundation: models, config, progress, output.
