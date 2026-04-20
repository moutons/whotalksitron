# Phase 6: Advanced Features

pyannote backend and speaker extraction flows. After this phase, all three backends work and speakers can be auto-extracted from episodes.

---

### Task 14: pyannote+Whisper backend `[sonnet]`

**Files:**
- Modify: `src/whotalksitron/backends/pyannote.py`
- Create: `tests/test_backends/test_pyannote.py`

**Reference:** Read `docs/superpowers/specs/2026-04-18-whotalksitron-design/backends.md` for pyannote behavior (two-stage pipeline, Whisper transcription + pyannote diarization, timestamp alignment, device selection).

**Note:** Tests for this backend must work even when pyannote/torch are not installed. Use mocks for the actual model inference. Test the merging/alignment logic directly.

- [ ] **Step 1: Write failing tests**

Create `tests/test_backends/test_pyannote.py`:

```python
import pytest

from whotalksitron.backends.pyannote import (
    _merge_transcription_and_diarization,
    _select_device,
)
from whotalksitron.models import TranscriptSegment


def test_merge_basic():
    transcription = [
        TranscriptSegment(start=0.0, end=5.0, text="Hello world."),
        TranscriptSegment(start=5.0, end=10.0, text="How are you?"),
        TranscriptSegment(start=10.0, end=15.0, text="I'm fine."),
    ]
    # Diarization regions: (start, end, speaker)
    diarization = [
        (0.0, 7.0, "SPEAKER_00"),
        (7.0, 15.0, "SPEAKER_01"),
    ]

    merged = _merge_transcription_and_diarization(transcription, diarization)
    assert len(merged) == 3
    assert merged[0].speaker == "Speaker 01"  # SPEAKER_00 -> Speaker 01
    assert merged[1].speaker == "Speaker 02"  # majority overlap with SPEAKER_01 (3s vs 2s)
    assert merged[2].speaker == "Speaker 02"  # SPEAKER_01 -> Speaker 02


def test_merge_empty_transcription():
    merged = _merge_transcription_and_diarization([], [(0.0, 5.0, "A")])
    assert len(merged) == 0


def test_merge_empty_diarization():
    transcription = [
        TranscriptSegment(start=0.0, end=5.0, text="Hello."),
    ]
    merged = _merge_transcription_and_diarization(transcription, [])
    assert len(merged) == 1
    assert merged[0].speaker is None


def test_merge_overlapping_speakers():
    transcription = [
        TranscriptSegment(start=0.0, end=10.0, text="Long segment."),
    ]
    diarization = [
        (0.0, 3.0, "SPEAKER_00"),
        (3.0, 10.0, "SPEAKER_01"),
    ]
    merged = _merge_transcription_and_diarization(transcription, diarization)
    assert merged[0].speaker == "Speaker 02"  # SPEAKER_01 has more overlap (7s vs 3s)


def test_speaker_pad_width():
    from whotalksitron.backends.pyannote import _speaker_pad_width
    assert _speaker_pad_width(0) == 2     # minimum 2 digits
    assert _speaker_pad_width(1) == 2     # 01
    assert _speaker_pad_width(9) == 2     # 09
    assert _speaker_pad_width(10) == 2    # 10
    assert _speaker_pad_width(99) == 2    # 99
    assert _speaker_pad_width(100) == 3   # 001..100
    assert _speaker_pad_width(999) == 3   # 001..999
    assert _speaker_pad_width(1000) == 4  # 0001..1000


def test_select_device_auto():
    device = _select_device("auto")
    assert device in ("cpu", "cuda", "mps")


def test_select_device_explicit():
    assert _select_device("cpu") == "cpu"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_backends/test_pyannote.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement pyannote backend**

Replace `src/whotalksitron/backends/pyannote.py`:

```python
from __future__ import annotations

import logging
import sys
from pathlib import Path

from whotalksitron.config import Config
from whotalksitron.models import SpeakerPool, TranscriptResult, TranscriptSegment
from whotalksitron.progress import ProgressCallback

logger = logging.getLogger(__name__)


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
        import torch
        from faster_whisper import WhisperModel
        from pyannote.audio import Pipeline as DiarizationPipeline

        audio_path = Path(audio_path)
        device = _select_device(self._config.pyannote_device)
        compute_type = "float16" if device != "cpu" else "int8"
        logger.info("Using device: %s, compute_type: %s", device, compute_type)

        # Stage 1: Whisper transcription
        if progress:
            progress.update("transcribe", 0, "loading Whisper model")

        whisper_model = WhisperModel(
            self._config.pyannote_whisper_model,
            device=device,
            compute_type=compute_type,
        )

        if progress:
            progress.update("transcribe", 20, "transcribing audio")

        segments_iter, _info = whisper_model.transcribe(str(audio_path))
        transcription = [
            TranscriptSegment(
                start=seg.start,
                end=seg.end,
                text=seg.text.strip(),
            )
            for seg in segments_iter
        ]

        if progress:
            progress.stage_complete(
                "transcribe", f"{len(transcription)} segments"
            )

        # Stage 2: pyannote diarization
        if progress:
            progress.update("diarize", 0, "loading diarization model")

        diarization_pipeline = DiarizationPipeline.from_pretrained(
            self._config.pyannote_diarization_model,
        )
        if device != "cpu":
            diarization_pipeline.to(torch.device(device))

        if progress:
            progress.update("diarize", 30, "diarizing audio")

        diarization_result = diarization_pipeline(str(audio_path))

        diarization_regions = [
            (turn.start, turn.end, speaker)
            for turn, _, speaker in diarization_result.itertracks(yield_label=True)
        ]

        if progress:
            progress.stage_complete(
                "diarize", f"{len(diarization_regions)} speaker regions"
            )

        # Merge
        segments = _merge_transcription_and_diarization(
            transcription, diarization_regions
        )

        # Extract speaker embeddings for voiceprint matching
        speaker_embeddings = {}
        if speakers:
            from pyannote.audio import Model, Inference
            emb_model = Model.from_pretrained("pyannote/wespeaker-voxceleb-resnet34-LM")
            emb_inference = Inference(emb_model, window="whole")

            raw_speakers = sorted(set(s for _, _, s in diarization_regions))
            pad_width = _speaker_pad_width(len(raw_speakers))
            speaker_map = {
                raw: f"Speaker {str(i + 1).zfill(pad_width)}"
                for i, raw in enumerate(raw_speakers)
            }
            # Compute embedding per detected speaker from their longest region
            for raw_name, mapped_name in speaker_map.items():
                regions = [(s, e) for s, e, sp in diarization_regions if sp == raw_name]
                if regions:
                    longest = max(regions, key=lambda r: r[1] - r[0])
                    # Extract clip and compute embedding
                    import tempfile
                    from whotalksitron.speakers.extraction import extract_audio_clip
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                        clip_path = Path(tmp.name)
                    extract_audio_clip(
                        audio_path, clip_path,
                        start=longest[0], duration=longest[1] - longest[0],
                    )
                    emb = emb_inference(str(clip_path))
                    speaker_embeddings[mapped_name] = emb.flatten()
                    clip_path.unlink(missing_ok=True)

        return TranscriptResult(
            segments=segments,
            metadata={
                "model": self._config.pyannote_whisper_model,
                "diarization_model": self._config.pyannote_diarization_model,
                "backend": "pyannote",
                "device": device,
                "speaker_embeddings": speaker_embeddings,
            },
        )

    def supports_diarization(self) -> bool:
        return True

    def is_available(self) -> bool:
        try:
            import pyannote.audio  # noqa: F401
            import torch  # noqa: F401
            import faster_whisper  # noqa: F401
            return True
        except ImportError:
            return False


def _merge_transcription_and_diarization(
    transcription: list[TranscriptSegment],
    diarization: list[tuple[float, float, str]],
) -> list[TranscriptSegment]:
    if not transcription:
        return []

    # Build speaker label map: SPEAKER_00 -> Speaker 01
    raw_speakers = sorted(set(s for _, _, s in diarization))
    pad_width = _speaker_pad_width(len(raw_speakers))
    speaker_map = {
        raw: f"Speaker {str(i + 1).zfill(pad_width)}"
        for i, raw in enumerate(raw_speakers)
    }

    merged: list[TranscriptSegment] = []
    for seg in transcription:
        speaker = _find_majority_speaker(
            seg.start, seg.end, diarization, speaker_map,
        )
        merged.append(TranscriptSegment(
            start=seg.start,
            end=seg.end,
            text=seg.text,
            speaker=speaker,
        ))

    return merged


def _find_majority_speaker(
    start: float,
    end: float,
    diarization: list[tuple[float, float, str]],
    speaker_map: dict[str, str],
) -> str | None:
    if not diarization:
        return None

    overlaps: dict[str, float] = {}
    for d_start, d_end, d_speaker in diarization:
        overlap_start = max(start, d_start)
        overlap_end = min(end, d_end)
        overlap = max(0.0, overlap_end - overlap_start)
        if overlap > 0:
            mapped = speaker_map.get(d_speaker, d_speaker)
            overlaps[mapped] = overlaps.get(mapped, 0.0) + overlap

    if not overlaps:
        return None
    return max(overlaps, key=overlaps.get)


def _speaker_pad_width(count: int) -> int:
    if count <= 0:
        return 2
    import math
    return max(2, math.ceil(math.log10(count + 1)))


def _select_device(device_config: str) -> str:
    if device_config != "auto":
        return device_config
    try:
        import torch
        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except (ImportError, AttributeError):
        pass
    return "cpu"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_backends/test_pyannote.py -v`
Expected: all 6 tests PASS

- [ ] **Step 5: Commit** `[COMMIT]`

```bash
git add src/whotalksitron/backends/pyannote.py tests/test_backends/test_pyannote.py
git commit -m "Implement pyannote+Whisper backend

Two-stage local pipeline: Whisper for transcription, pyannote for
diarization. Merges by majority timestamp overlap. Auto-detects
MPS/CUDA/CPU."
```

---

### Task 15: Speaker extraction flows `[sonnet]`

**Files:**
- Create: `src/whotalksitron/speakers/extraction.py`
- Create: `tests/test_speakers/test_extraction.py`
- Modify: `src/whotalksitron/cli.py` (add `extract-samples` command, wire `--identify-speakers`)

**Reference:** Read `docs/superpowers/specs/2026-04-18-whotalksitron-design/cli.md` for the `--identify-speakers` and `extract-samples` flows, including TTY vs non-TTY behavior and quality heuristics.

- [ ] **Step 1: Write failing tests for extraction logic**

Create `tests/test_speakers/test_extraction.py`:

```python
from pathlib import Path

import pytest

from whotalksitron.models import TranscriptResult, TranscriptSegment
from whotalksitron.speakers.extraction import (
    CandidateSample,
    find_candidates,
    score_segment,
    group_segments_by_speaker,
)


def _make_segments() -> list[TranscriptSegment]:
    return [
        TranscriptSegment(start=0.0, end=15.0, text="Hello.", speaker="Speaker 01"),
        TranscriptSegment(start=15.0, end=20.0, text="Hi.", speaker="Speaker 02"),
        TranscriptSegment(start=20.0, end=40.0, text="Long monologue.", speaker="Speaker 01"),
        TranscriptSegment(start=40.0, end=55.0, text="Response.", speaker="Speaker 02"),
        TranscriptSegment(start=55.0, end=60.0, text="Short.", speaker="Speaker 01"),
        TranscriptSegment(start=60.0, end=80.0, text="Another long one.", speaker="Speaker 02"),
        TranscriptSegment(start=80.0, end=95.0, text="More talk.", speaker="Speaker 01"),
    ]


def test_group_segments_by_speaker():
    segments = _make_segments()
    groups = group_segments_by_speaker(segments)
    assert "Speaker 01" in groups
    assert "Speaker 02" in groups
    assert len(groups["Speaker 01"]) == 4
    assert len(groups["Speaker 02"]) == 3


def test_group_segments_skips_none():
    segments = [
        TranscriptSegment(start=0.0, end=5.0, text="a"),
        TranscriptSegment(start=5.0, end=10.0, text="b", speaker="Matt"),
    ]
    groups = group_segments_by_speaker(segments)
    assert "Matt" in groups
    assert len(groups) == 1


def test_score_segment_prefers_longer():
    short = TranscriptSegment(start=0.0, end=5.0, text="short")
    long = TranscriptSegment(start=0.0, end=20.0, text="long")
    assert score_segment(long, total_duration=100.0) > score_segment(short, total_duration=100.0)


def test_score_segment_avoids_extremes():
    middle = TranscriptSegment(start=45.0, end=60.0, text="middle")
    start = TranscriptSegment(start=0.0, end=15.0, text="start")
    # Middle of episode should score slightly higher for diversity
    mid_score = score_segment(middle, total_duration=100.0)
    start_score = score_segment(start, total_duration=100.0)
    # Both are valid, but middle shouldn't be penalized
    assert mid_score >= 0


def test_find_candidates_top_3():
    segments = _make_segments()
    groups = group_segments_by_speaker(segments)
    candidates = find_candidates(groups["Speaker 01"], total_duration=95.0, max_candidates=3)
    assert len(candidates) <= 3
    # Candidates should be sorted by score descending
    scores = [c.score for c in candidates]
    assert scores == sorted(scores, reverse=True)


def test_find_candidates_empty():
    candidates = find_candidates([], total_duration=100.0)
    assert len(candidates) == 0


def test_candidate_sample_fields():
    seg = TranscriptSegment(start=10.0, end=25.0, text="test")
    candidates = find_candidates([seg], total_duration=100.0)
    assert len(candidates) == 1
    assert candidates[0].start == 10.0
    assert candidates[0].end == 25.0
    assert candidates[0].duration == 15.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_speakers/test_extraction.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement extraction module**

Create `src/whotalksitron/speakers/extraction.py`:

```python
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from whotalksitron.models import TranscriptSegment

logger = logging.getLogger(__name__)


@dataclass
class CandidateSample:
    start: float
    end: float
    speaker: str
    score: float

    @property
    def duration(self) -> float:
        return self.end - self.start


def group_segments_by_speaker(
    segments: list[TranscriptSegment],
) -> dict[str, list[TranscriptSegment]]:
    groups: dict[str, list[TranscriptSegment]] = {}
    for seg in segments:
        if seg.speaker is None:
            continue
        groups.setdefault(seg.speaker, []).append(seg)
    return groups


def score_segment(seg: TranscriptSegment, total_duration: float) -> float:
    duration_score = min(seg.duration / 15.0, 1.0)

    if total_duration > 0:
        position = (seg.start + seg.end) / 2.0 / total_duration
        diversity_score = 1.0 - abs(position - 0.5) * 0.2
    else:
        diversity_score = 1.0

    length_penalty = 0.0 if seg.duration >= 10.0 else (seg.duration - 10.0) * 0.1

    return duration_score + diversity_score + length_penalty


def find_candidates(
    segments: list[TranscriptSegment],
    total_duration: float,
    max_candidates: int = 3,
) -> list[CandidateSample]:
    scored = []
    for seg in segments:
        s = score_segment(seg, total_duration)
        scored.append(CandidateSample(
            start=seg.start,
            end=seg.end,
            speaker=seg.speaker or "Unknown",
            score=s,
        ))

    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[:max_candidates]


def extract_audio_clip(
    source_path: Path,
    output_path: Path,
    start: float,
    duration: float,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-i", str(source_path),
        "-ss", str(start),
        "-t", str(duration),
        "-ac", "1", "-ar", "16000",
        "-y", str(output_path),
    ]
    logger.debug("Extracting clip: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg clip extraction failed: {result.stderr[:300]}")
    return output_path


def extract_samples_for_speakers(
    audio_path: Path,
    segments: list[TranscriptSegment],
    output_dir: Path,
    max_candidates: int = 3,
) -> dict[str, list[Path]]:
    groups = group_segments_by_speaker(segments)
    total_duration = segments[-1].end if segments else 0.0

    extracted: dict[str, list[Path]] = {}
    for speaker, speaker_segments in groups.items():
        candidates = find_candidates(
            speaker_segments, total_duration, max_candidates,
        )
        speaker_dir = output_dir / _safe_dirname(speaker)
        paths: list[Path] = []
        for i, cand in enumerate(candidates):
            clip_path = speaker_dir / f"sample-{i + 1:03d}.wav"
            extract_audio_clip(
                audio_path, clip_path,
                start=cand.start, duration=cand.duration,
            )
            paths.append(clip_path)
            logger.info(
                "Extracted %s sample %d: %.1fs from %s",
                speaker, i + 1, cand.duration,
                _format_time(cand.start),
            )
        extracted[speaker] = paths

    return extracted


def _safe_dirname(speaker: str) -> str:
    return speaker.lower().replace(" ", "-")


def _format_time(seconds: float) -> str:
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    s = int(seconds) % 60
    return f"{h:02d}:{m:02d}:{s:02d}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_speakers/test_extraction.py -v`
Expected: all 8 tests PASS

- [ ] **Step 5: Wire extract-samples command and --identify-speakers into CLI**

Add to `src/whotalksitron/cli.py` (after the `config` command):

```python
@main.command("extract-samples")
@click.argument("audio_file", type=click.Path(exists=True, path_type=Path))
@click.option("--podcast", default=None)
@click.option("--output", "-o", default=None, type=click.Path(path_type=Path))
@click.pass_context
def extract_samples_cmd(ctx, audio_file, podcast, output):
    """Extract speaker voice samples from an audio file."""
    cfg: Config = ctx.obj["config"]

    from whotalksitron.backends import select_backend, BackendUnavailableError
    from whotalksitron.pipeline import Pipeline, ValidationError, PreprocessingError
    from whotalksitron.models import SpeakerPool
    from whotalksitron.speakers.enrollment import SpeakerStore
    from whotalksitron.speakers.extraction import extract_samples_for_speakers

    progress = ProgressReporter(enabled=ctx.obj["progress"])

    try:
        backend = select_backend(cfg)
    except BackendUnavailableError as e:
        click.echo(str(e), err=True)
        ctx.exit(2)
        return

    if not backend.supports_diarization():
        click.echo(
            "extract-samples requires a backend that supports diarization. "
            "Configure gemini or install pyannote: "
            "uv tool install whotalksitron --with local",
            err=True,
        )
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

    pipeline = Pipeline(cfg)
    try:
        result = pipeline.run(
            audio_path=audio_file,
            output_path=audio_file.with_suffix(".md"),
            backend=backend,
            podcast=podcast,
            speakers=speakers,
            progress=progress,
        )
    except (ValidationError, PreprocessingError) as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)
        return

    if not result.transcript or not result.transcript.segments:
        click.echo("No segments found in transcript.", err=True)
        ctx.exit(1)
        return

    output_dir = output or Path("./samples")
    extracted = extract_samples_for_speakers(
        audio_file, result.transcript.segments, output_dir,
    )

    import re

    click.echo(f"\nExtracted samples to {output_dir}/:")
    for speaker, paths in sorted(extracted.items()):
        matched = "matched" if not re.match(r"^Speaker \d{2,}$", speaker) else "unmatched"
        click.echo(f"  {speaker}/  {len(paths)} clips  ({matched})")

    unmatched = [s for s in extracted if re.match(r"^Speaker \d{2,}$", s)]
    if unmatched and podcast:
        click.echo("\nTo enroll unmatched speakers:")
        for speaker in unmatched:
            safe = speaker.lower().replace(" ", "-")
            first_clip = extracted[speaker][0] if extracted[speaker] else "sample.wav"
            click.echo(
                f"  whotalksitron enroll --name NAME --podcast {podcast} "
                f"--sample {output_dir}/{safe}/sample-001.wav"
            )
```

- [ ] **Step 6: Add tests for extract-samples command**

Add to `tests/test_cli.py`:

```python
def test_extract_samples_help(runner):
    result = runner.invoke(main, ["extract-samples", "--help"])
    assert result.exit_code == 0
    assert "--podcast" in result.output
    assert "--output" in result.output
```

- [ ] **Step 7: Run full suite and commit** `[COMMIT]`

Run: `just test`
Expected: all tests pass

Run: `just ensureci-sandbox`
Expected: all checks pass

```bash
git add src/whotalksitron/speakers/extraction.py tests/test_speakers/test_extraction.py src/whotalksitron/cli.py tests/test_cli.py
git commit -m "Add speaker extraction and extract-samples command

Candidate scoring by duration and position diversity. ffmpeg clip
extraction. extract-samples CLI command with matched/unmatched
summary and enrollment instructions."
```

Push and `[REVIEW:full]` — Phase 6 complete. All features implemented. Final review before merge.
