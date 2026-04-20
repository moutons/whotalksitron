# Phase 5: Integration

Pipeline orchestration and CLI wiring. After this phase, `whotalksitron transcribe`, `enroll`, `import-speaker`, `list-speakers`, and `config` all work end-to-end.

---

### Task 12: Pipeline orchestration `[sonnet]`

**Files:**
- Create: `src/whotalksitron/pipeline.py`
- Create: `tests/test_pipeline.py`

**Reference:** Read `docs/superpowers/specs/2026-04-18-whotalksitron-design/pipeline.md` for the 6-stage flow (validate → preprocess → transcribe → voiceprint → format → write).

- [ ] **Step 1: Write failing tests**

Create `tests/test_pipeline.py`:

```python
import io
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from whotalksitron.config import Config
from whotalksitron.models import SpeakerPool, TranscriptResult, TranscriptSegment
from whotalksitron.pipeline import (
    Pipeline,
    ValidationError,
    PreprocessingError,
    validate_audio,
    check_ffmpeg,
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
    # May or may not be available in test env
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
            TranscriptSegment(start=5.0, end=10.0, text="World.", speaker="Speaker 01"),
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

    # Segments without speaker attribution despite enrolled speakers = partial
    result = pipeline.run(
        audio_path=fake_audio,
        output_path=output_path,
        backend=mock_backend,
        podcast="atp",
        speakers=SpeakerPool(podcast="atp", speakers={"matt": []}),
    )

    assert output_path.exists()
    # Speakers enrolled but segment has no speaker attribution = degraded
    assert result.exit_code == 3
    assert result.warnings
    assert "could not be matched" in result.warnings[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement pipeline**

Create `src/whotalksitron/pipeline.py`:

```python
from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from whotalksitron.backends import Backend
from whotalksitron.config import Config
from whotalksitron.models import SpeakerPool, TranscriptResult
from whotalksitron.output import render_transcript
from whotalksitron.progress import ProgressReporter

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    pass


class PreprocessingError(Exception):
    pass


@dataclass
class PipelineResult:
    exit_code: int
    transcript: TranscriptResult | None = None
    output_path: Path | None = None
    warnings: list[str] | None = None


class Pipeline:
    def __init__(self, config: Config) -> None:
        self._config = config

    def run(
        self,
        audio_path: Path,
        output_path: Path,
        backend: Backend,
        podcast: str | None,
        speakers: SpeakerPool | None,
        progress: ProgressReporter | None = None,
    ) -> PipelineResult:
        warnings: list[str] = []

        # Stage 1: Validate
        try:
            info = validate_audio(audio_path)
            if progress:
                size_mb = info["size_bytes"] / (1024 * 1024)
                progress.stage_complete(
                    "validate", f"{audio_path.name}, {size_mb:.1f}MB"
                )
        except ValidationError:
            raise

        # Stage 2: Preprocess
        processed_path = audio_path
        if self._needs_conversion(audio_path, backend):
            if not check_ffmpeg():
                raise PreprocessingError(
                    "ffmpeg is required to convert audio files. "
                    "Install: brew install ffmpeg"
                )
            processed_path = self._convert_audio(audio_path)
            if progress:
                progress.stage_complete("preprocess", "converted to WAV")
        else:
            if progress:
                progress.stage_complete("preprocess", "skipped, native format")

        # Stage 3: Transcribe
        transcript = backend.transcribe(
            processed_path,
            speakers=speakers,
            progress=progress,
        )

        # Stage 4: Voiceprint matching
        if speakers and speakers.speakers:
            if progress:
                progress.update("voiceprint", 0, "matching speakers")
            transcript = self._match_voiceprints(
                transcript, speakers, backend, progress
            )
        else:
            if progress:
                progress.stage_complete("voiceprint", "skipped, no speakers enrolled")

        # Check for degraded quality: speakers were enrolled but some remain unmatched
        if speakers and speakers.speakers and transcript.unmatched_speakers:
            warnings.append(
                f"{len(transcript.unmatched_speakers)} speakers could not be matched. "
                "Run `whotalksitron enroll --rebuild` or add more samples."
            )

        # Stage 5: Format
        if progress:
            progress.update("format", 0, "rendering markdown")
        markdown = render_transcript(
            transcript,
            source_file=audio_path.name,
            podcast=podcast,
        )
        if progress:
            progress.stage_complete("format", "markdown rendered")

        # Stage 6: Write
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown)
        if progress:
            progress.stage_complete("write", str(output_path))

        logger.info("Transcript written to %s", output_path)

        exit_code = 0
        if warnings:
            exit_code = 3

        return PipelineResult(
            exit_code=exit_code,
            transcript=transcript,
            output_path=output_path,
            warnings=warnings,
        )

    def _needs_conversion(self, audio_path: Path, backend: Backend) -> bool:
        native_formats = {".mp3", ".wav", ".flac", ".m4a", ".webm", ".ogg"}
        if backend.name == "gemini":
            return audio_path.suffix.lower() not in native_formats
        # Local backends always want 16kHz mono WAV
        return audio_path.suffix.lower() != ".wav"

    def _convert_audio(self, audio_path: Path) -> Path:
        output = audio_path.with_suffix(".converted.wav")
        cmd = [
            "ffmpeg", "-i", str(audio_path),
            "-ac", "1", "-ar", "16000",
            "-y", str(output),
        ]
        logger.debug("Running: %s", " ".join(cmd))
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            raise PreprocessingError(
                f"ffmpeg conversion failed: {result.stderr[:500]}"
            )
        return output

    def _match_voiceprints(
        self,
        transcript: TranscriptResult,
        speakers: SpeakerPool,
        backend: Backend,
        progress: ProgressReporter | None,
    ) -> TranscriptResult:
        from whotalksitron.speakers.enrollment import SpeakerStore
        from whotalksitron.speakers.matching import SpeakerEmbeddings, match_speakers
        from whotalksitron.speakers.embeddings import load_embedding

        # Load enrolled speaker embeddings
        enrolled: dict = {}
        store = SpeakerStore(self._config.speakers_dir)
        for name in speakers.speakers:
            emb_path = store.embedding_path(name, speakers.podcast)
            emb = load_embedding(emb_path)
            if emb is not None:
                enrolled[name] = emb

        if not enrolled:
            if progress:
                progress.stage_complete("voiceprint", "no embeddings found")
            return transcript

        # Build detected speaker embeddings from transcript segments.
        # For each generic "Speaker N" label, we need their embedding.
        # The pyannote backend computes these during diarization.
        # The Gemini backend handles matching internally (samples in prompt).
        # If the backend didn't provide detected embeddings in metadata,
        # we can't match — return the transcript as-is.
        detected: dict = transcript.metadata.get("speaker_embeddings", {})

        if not detected:
            logger.info(
                "No detected speaker embeddings available. "
                "Voiceprint matching skipped for this backend."
            )
            if progress:
                progress.stage_complete("voiceprint", "no detected embeddings")
            return transcript

        if progress:
            progress.stage_complete(
                "voiceprint",
                f"{len(enrolled)} enrolled, {len(detected)} detected",
            )

        speaker_embeddings = SpeakerEmbeddings(enrolled=enrolled, detected=detected)
        return match_speakers(
            transcript, speaker_embeddings, self._config.match_threshold,
        )


def validate_audio(path: Path) -> dict:
    if not path.exists():
        raise ValidationError(f"Audio file not found: {path}")
    if path.stat().st_size == 0:
        raise ValidationError(f"Audio file is empty: {path}")
    return {
        "path": path,
        "size_bytes": path.stat().st_size,
        "suffix": path.suffix,
    }


def check_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: all 6 tests PASS

- [ ] **Step 5: Commit** `[COMMIT]`

```bash
git add src/whotalksitron/pipeline.py tests/test_pipeline.py
git commit -m "Add pipeline orchestration

Six-stage flow: validate, preprocess, transcribe, voiceprint match,
format, write. Handles ffmpeg conversion and backend delegation."
```

---

### Task 13: CLI wiring `[sonnet]`

**Files:**
- Modify: `src/whotalksitron/cli.py`
- Modify: `tests/test_cli.py`

**Reference:** Read `docs/superpowers/specs/2026-04-18-whotalksitron-design/cli.md` for command surface, global flags, and all subcommands.

- [ ] **Step 1: Write failing tests for all commands**

Replace `tests/test_cli.py`:

```python
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from whotalksitron.cli import main


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def fake_audio(tmp_path) -> Path:
    audio = tmp_path / "episode.mp3"
    audio.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 1000)
    return audio


import pytest


def test_cli_help(runner):
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "Audio transcription CLI" in result.output


def test_cli_version(runner):
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_transcribe_help(runner):
    result = runner.invoke(main, ["transcribe", "--help"])
    assert result.exit_code == 0
    assert "--backend" in result.output
    assert "--podcast" in result.output
    assert "--output" in result.output


def test_enroll_help(runner):
    result = runner.invoke(main, ["enroll", "--help"])
    assert result.exit_code == 0
    assert "--name" in result.output
    assert "--podcast" in result.output
    assert "--sample" in result.output


def test_list_speakers_help(runner):
    result = runner.invoke(main, ["list-speakers", "--help"])
    assert result.exit_code == 0


def test_import_speaker_help(runner):
    result = runner.invoke(main, ["import-speaker", "--help"])
    assert result.exit_code == 0
    assert "--name" in result.output
    assert "--from" in result.output
    assert "--to" in result.output


def test_config_help(runner):
    result = runner.invoke(main, ["config", "--help"])
    assert result.exit_code == 0
    assert "--show" in result.output
    assert "--init" in result.output


def test_config_init(runner, tmp_path):
    config_file = tmp_path / "config.toml"
    result = runner.invoke(main, ["config", "--init"], env={
        "WHOTALKSITRON_CONFIG": str(config_file),
    })
    assert result.exit_code == 0
    assert config_file.exists()


def test_config_show(runner, tmp_path):
    config_file = tmp_path / "config.toml"
    # init first
    runner.invoke(main, ["config", "--init"], env={
        "WHOTALKSITRON_CONFIG": str(config_file),
    })
    result = runner.invoke(main, ["config", "--show"], env={
        "WHOTALKSITRON_CONFIG": str(config_file),
    })
    assert result.exit_code == 0
    assert "backend" in result.output


def test_enroll_creates_speaker(runner, tmp_path, fake_audio):
    speakers_dir = tmp_path / "speakers"
    result = runner.invoke(main, [
        "enroll", "--name", "matt", "--podcast", "atp",
        "--sample", str(fake_audio),
    ], env={"WHOTALKSITRON_SPEAKERS_DIR": str(speakers_dir)})
    assert result.exit_code == 0
    assert (speakers_dir / "atp" / "matt" / "samples").exists()


def test_list_speakers_empty(runner, tmp_path):
    speakers_dir = tmp_path / "speakers"
    result = runner.invoke(main, ["list-speakers"], env={
        "WHOTALKSITRON_SPEAKERS_DIR": str(speakers_dir),
    })
    assert result.exit_code == 0
    assert "No speakers enrolled" in result.output


def test_config_set(runner, tmp_path):
    config_file = tmp_path / "config.toml"
    runner.invoke(main, ["config", "--init"], env={
        "WHOTALKSITRON_CONFIG": str(config_file),
    })
    result = runner.invoke(main, ["config", "--set", "gemini.model=gemini-2.5-pro"], env={
        "WHOTALKSITRON_CONFIG": str(config_file),
    })
    assert result.exit_code == 0
    assert "Set gemini.model" in result.output

    import tomllib
    with open(config_file, "rb") as f:
        data = tomllib.load(f)
    assert data["gemini"]["model"] == "gemini-2.5-pro"


def test_config_set_malformed(runner, tmp_path):
    config_file = tmp_path / "config.toml"
    runner.invoke(main, ["config", "--init"], env={
        "WHOTALKSITRON_CONFIG": str(config_file),
    })
    result = runner.invoke(main, ["config", "--set", "noequals"], env={
        "WHOTALKSITRON_CONFIG": str(config_file),
    })
    assert result.exit_code == 2
    assert "Invalid format" in result.output


def test_config_set_boolean_coercion(runner, tmp_path):
    config_file = tmp_path / "config.toml"
    runner.invoke(main, ["config", "--init"], env={
        "WHOTALKSITRON_CONFIG": str(config_file),
    })
    result = runner.invoke(main, ["config", "--set", "defaults.progress=true"], env={
        "WHOTALKSITRON_CONFIG": str(config_file),
    })
    assert result.exit_code == 0

    import tomllib
    with open(config_file, "rb") as f:
        data = tomllib.load(f)
    assert data["defaults"]["progress"] is True


def test_config_set_no_config_file(runner, tmp_path):
    result = runner.invoke(main, ["config", "--set", "gemini.model=test"], env={
        "WHOTALKSITRON_CONFIG": str(tmp_path / "nonexistent.toml"),
    })
    assert result.exit_code == 1
    assert "No config file" in result.output


def test_transcribe_identify_speakers_flag(runner):
    result = runner.invoke(main, ["transcribe", "--help"])
    assert "--identify-speakers" in result.output


def test_global_flags(runner):
    result = runner.invoke(main, ["--log-level", "debug", "--help"])
    assert result.exit_code == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL — missing commands

- [ ] **Step 3: Implement full CLI**

Replace `src/whotalksitron/cli.py`:

```python
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import click

from whotalksitron import __version__
from whotalksitron.config import Config, load_config
from whotalksitron.progress import ProgressReporter


def _setup_logging(level: str, fmt: str) -> None:
    numeric = getattr(logging, level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stderr)
    if fmt == "json":
        import json

        class JsonFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                return json.dumps({
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                })

        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(levelname)s %(name)s: %(message)s")
        )
    logging.root.handlers.clear()
    logging.root.addHandler(handler)
    logging.root.setLevel(numeric)


@click.group()
@click.version_option(version=__version__)
@click.option("--log-level", default=None,
              type=click.Choice(["debug", "info", "warn", "error"]))
@click.option("--log-format", default=None,
              type=click.Choice(["text", "json"]))
@click.option("--progress", is_flag=True, default=False)
@click.option("--quiet", "-q", is_flag=True, default=False)
@click.pass_context
def main(ctx: click.Context, log_level, log_format, progress, quiet) -> None:
    """Audio transcription CLI with speaker identification."""
    ctx.ensure_object(dict)
    ctx.obj["cli_overrides"] = {}
    if log_level:
        ctx.obj["cli_overrides"]["log_level"] = log_level
    if log_format:
        ctx.obj["cli_overrides"]["log_format"] = log_format

    config_path = os.environ.get("WHOTALKSITRON_CONFIG")
    cfg = load_config(
        config_path=Path(config_path) if config_path else None,
        cli_overrides=ctx.obj["cli_overrides"],
    )

    effective_level = log_level or cfg.log_level
    effective_format = log_format or cfg.log_format
    _setup_logging(effective_level, effective_format)

    ctx.obj["config"] = cfg
    ctx.obj["progress"] = progress or cfg.progress
    ctx.obj["quiet"] = quiet


@main.command()
@click.argument("audio_file", type=click.Path(exists=True, path_type=Path))
@click.option("--backend", type=click.Choice(["gemini", "pyannote", "whisper"]))
@click.option("--podcast", default=None)
@click.option("--output", "-o", default=None, type=click.Path(path_type=Path))
@click.option("--model", default=None)
@click.option("--identify-speakers", is_flag=True, default=False)
@click.pass_context
def transcribe(ctx, audio_file, backend, podcast, output, model, identify_speakers):
    """Transcribe an audio file to markdown."""
    cfg: Config = ctx.obj["config"]

    if backend:
        cfg.backend = backend
    if model:
        cfg.gemini_model = model
        cfg.whisper_model = model

    from whotalksitron.backends import select_backend, BackendUnavailableError
    from whotalksitron.pipeline import Pipeline, ValidationError, PreprocessingError
    from whotalksitron.models import SpeakerPool
    from whotalksitron.speakers.enrollment import SpeakerStore

    progress = ProgressReporter(enabled=ctx.obj["progress"])

    try:
        selected = select_backend(cfg)
    except BackendUnavailableError as e:
        click.echo(str(e), err=True)
        ctx.exit(2)
        return

    speakers = None
    if podcast:
        store = SpeakerStore(_speakers_dir())
        speaker_list = store.list_speakers(podcast=podcast)
        if podcast in speaker_list:
            sample_map = {}
            for name in speaker_list[podcast]:
                sample_map[name] = store.get_sample_paths(name, podcast)
            speakers = SpeakerPool(podcast=podcast, speakers=sample_map)

    if output is None:
        output = audio_file.with_suffix(".md")

    pipeline = Pipeline(cfg)
    try:
        result = pipeline.run(
            audio_path=audio_file,
            output_path=output,
            backend=selected,
            podcast=podcast,
            speakers=speakers,
            progress=progress,
        )
    except (ValidationError, PreprocessingError) as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)
        return

    if identify_speakers and result.transcript:
        _run_identify_speakers(
            result.transcript, audio_file, output, podcast, ctx,
        )

    if not ctx.obj["quiet"]:
        click.echo(f"Wrote {output}")
        if result.warnings:
            for w in result.warnings:
                click.echo(f"Warning: {w}", err=True)

    ctx.exit(result.exit_code)


def _run_identify_speakers(
    transcript, audio_path, output_path, podcast, ctx,
):
    """Interactive speaker identification after transcription."""
    import re
    import sys
    from whotalksitron.speakers.extraction import (
        extract_samples_for_speakers,
        group_segments_by_speaker,
        find_candidates,
    )
    from whotalksitron.speakers.enrollment import SpeakerStore
    from whotalksitron.output import render_transcript

    unmatched = sorted(
        s for s in transcript.speakers
        if re.match(r"^Speaker \d{2,}$", s)
    )
    if not unmatched:
        return

    click.echo(f"\n{len(unmatched)} unmatched speakers detected.")

    if not sys.stdin.isatty():
        staging_dir = (
            Path.home() / ".config" / "whotalksitron" / "staging"
            / audio_path.stem
        )
        extracted = extract_samples_for_speakers(
            audio_path, transcript.segments, staging_dir,
        )
        click.echo(f"Not a TTY. Extracted samples to:")
        for speaker, paths in sorted(extracted.items()):
            if speaker in unmatched:
                click.echo(f"  {staging_dir / speaker.lower().replace(' ', '-')}/")
        click.echo("Run `whotalksitron enroll` with these samples to identify them.")
        return

    import platform
    play_cmd = "afplay" if platform.system() == "Darwin" else "aplay"

    groups = group_segments_by_speaker(transcript.segments)
    store = SpeakerStore(_speakers_dir())
    relabel_map: dict[str, str] = {}

    for speaker in sorted(unmatched):
        speaker_segs = groups.get(speaker, [])
        if not speaker_segs:
            continue

        total_time = sum(s.duration for s in speaker_segs)
        candidates = find_candidates(speaker_segs, transcript.duration)

        click.echo(f"\n--- {speaker}: {len(speaker_segs)} segments, "
                    f"{total_time:.0f}s total speaking time ---")

        for cand in candidates:
            import subprocess
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                clip_path = Path(tmp.name)

            from whotalksitron.speakers.extraction import extract_audio_clip
            extract_audio_clip(audio_path, clip_path, cand.start, cand.duration)

            click.echo(f"Playing sample ({cand.duration:.0f}s from "
                        f"{_format_ts(cand.start)})...")
            subprocess.run([play_cmd, str(clip_path)], check=False,
                           capture_output=True)

            response = click.prompt(
                "Identify this speaker (name, Enter to skip, "
                "'r' to replay, 'n' for next sample)",
                default="", show_default=False,
            )

            if response == "r":
                subprocess.run([play_cmd, str(clip_path)], check=False,
                               capture_output=True)
                response = click.prompt("Identify this speaker", default="",
                                        show_default=False)

            if response and response not in ("n", ""):
                if podcast:
                    store.enroll(response, podcast, clip_path,
                                 compute_embedding=False)
                    clip_path.unlink(missing_ok=True)
                    # Extract and enroll all remaining candidate clips
                    for extra_cand in candidates:
                        if extra_cand is cand:
                            continue
                        with tempfile.NamedTemporaryFile(suffix=".wav",
                                                         delete=False) as tmp2:
                            extra_path = Path(tmp2.name)
                        extract_audio_clip(audio_path, extra_path,
                                           extra_cand.start, extra_cand.duration)
                        store.enroll(response, podcast, extra_path,
                                     compute_embedding=False)
                        extra_path.unlink(missing_ok=True)
                else:
                    clip_path.unlink(missing_ok=True)

                relabel_map[speaker] = response
                click.echo(f'Enrolled "{response}" for podcast "{podcast}"')
                break

            clip_path.unlink(missing_ok=True)

            if response == "n":
                continue
            if response == "":
                click.echo(f"Skipped. {speaker} remains unlabeled.")
                break

    if relabel_map:
        from whotalksitron.models import TranscriptSegment, TranscriptResult
        new_segments = []
        for seg in transcript.segments:
            speaker = relabel_map.get(seg.speaker, seg.speaker) if seg.speaker else None
            new_segments.append(TranscriptSegment(
                start=seg.start, end=seg.end, text=seg.text, speaker=speaker,
            ))
        new_transcript = TranscriptResult(segments=new_segments,
                                           metadata=transcript.metadata)
        markdown = render_transcript(new_transcript, audio_path.name, podcast)
        output_path.write_text(markdown)
        click.echo("Transcript updated with new speaker labels.")


def _format_ts(seconds: float) -> str:
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    s = int(seconds) % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


@main.command()
@click.option("--name", required=True)
@click.option("--podcast", required=True)
@click.option("--sample", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--rebuild", is_flag=True, default=False)
@click.pass_context
def enroll(ctx, name, podcast, sample, rebuild):
    """Enroll a speaker voice sample."""
    from whotalksitron.speakers.enrollment import SpeakerStore

    store = SpeakerStore(_speakers_dir())

    if rebuild:
        click.echo(f"Rebuilding embeddings for {name!r} in {podcast!r}...")
        store.rebuild_embeddings(name, podcast)
        click.echo("Rebuild complete.")
        return

    store.enroll(name, podcast, sample)
    meta = store.get_meta(name, podcast)
    count = meta.get("sample_count", 1)
    click.echo(f'Enrolled "{name}" for podcast "{podcast}" ({count} samples)')


@main.command("import-speaker")
@click.option("--name", required=True)
@click.option("--from", "from_podcast", required=True)
@click.option("--to", "to_podcast", required=True)
@click.pass_context
def import_speaker_cmd(ctx, name, from_podcast, to_podcast):
    """Import a speaker from one podcast to another."""
    from whotalksitron.speakers.enrollment import SpeakerStore

    store = SpeakerStore(_speakers_dir())
    try:
        store.import_speaker(name, from_podcast=from_podcast, to_podcast=to_podcast)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)
        return

    click.echo(f'Imported "{name}" from "{from_podcast}" to "{to_podcast}"')


@main.command("list-speakers")
@click.option("--podcast", default=None)
@click.pass_context
def list_speakers_cmd(ctx, podcast):
    """List enrolled speakers."""
    from whotalksitron.speakers.enrollment import SpeakerStore

    store = SpeakerStore(_speakers_dir())
    speakers = store.list_speakers(podcast=podcast)

    if not speakers:
        click.echo("No speakers enrolled.")
        return

    for pod, names in sorted(speakers.items()):
        click.echo(f"{pod}:")
        for name in names:
            meta = store.get_meta(name, pod)
            count = meta.get("sample_count", 0)
            click.echo(f"  {name} ({count} samples)")


@main.command()
@click.option("--show", is_flag=True, default=False)
@click.option("--set", "set_value", default=None)
@click.option("--init", "init_config", is_flag=True, default=False)
@click.pass_context
def config(ctx, show, set_value, init_config):
    """Manage configuration."""
    cfg: Config = ctx.obj["config"]

    if init_config:
        config_path = _config_path()
        if config_path.exists():
            click.echo(f"Config already exists: {config_path}", err=True)
            ctx.exit(1)
            return
        cfg.write_default(config_path)
        click.echo(f"Created {config_path}")
        return

    if show:
        click.echo(cfg.show())
        return

    if set_value:
        config_path = _config_path()
        if not config_path.exists():
            click.echo("No config file. Run `whotalksitron config --init` first.", err=True)
            ctx.exit(1)
            return

        key, _, value = set_value.partition("=")
        if not value:
            click.echo(f"Invalid format. Use: --set key=value", err=True)
            ctx.exit(2)
            return

        import tomllib
        with open(config_path, "rb") as f:
            data = tomllib.load(f)

        parts = key.split(".")
        target = data
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = _coerce_value(value)

        import tomli_w
        with open(config_path, "wb") as f:
            tomli_w.dump(data, f)
        click.echo(f"Set {key} = {value}")
        return

    click.echo("Use --show, --set, or --init. Run --help for details.")


def _speakers_dir() -> Path:
    env = os.environ.get("WHOTALKSITRON_SPEAKERS_DIR")
    if env:
        return Path(env)
    return Path.home() / ".config" / "whotalksitron" / "speakers"


def _config_path() -> Path:
    env = os.environ.get("WHOTALKSITRON_CONFIG")
    if env:
        return Path(env)
    return Path.home() / ".config" / "whotalksitron" / "config.toml"


def _coerce_value(value: str) -> object:
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: all 13 tests PASS

- [ ] **Step 5: Run full suite and commit** `[COMMIT]`

Run: `just test`
Expected: all tests pass

Run: `just ensureci-sandbox`
Expected: all checks pass

```bash
git add src/whotalksitron/cli.py tests/test_cli.py
git commit -m "Wire CLI commands

All subcommands: transcribe, enroll, import-speaker, list-speakers,
config. Global flags for log-level, log-format, progress, quiet.
Config and speaker directory overridable via env vars for testing."
```

Push and `[REVIEW:full]` — Phase 5 complete. End-to-end integration point. Full review of architecture, CLI surface, pipeline, and test coverage.
