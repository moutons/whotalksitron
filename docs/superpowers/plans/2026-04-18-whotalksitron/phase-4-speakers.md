# Phase 4: Speaker System

Speaker enrollment, embedding computation, and voiceprint matching. After this phase, speakers can be enrolled per podcast and matched against transcript segments.

---

### Task 9: Speaker enrollment and storage `[sonnet]`

**Files:**
- Create: `src/whotalksitron/speakers/__init__.py`
- Create: `src/whotalksitron/speakers/enrollment.py`
- Create: `tests/test_speakers/__init__.py`
- Create: `tests/test_speakers/test_enrollment.py`

**Reference:** Read `docs/superpowers/specs/2026-04-18-whotalksitron-design/speakers.md` for data layout, enrollment flow, import behavior.

- [ ] **Step 1: Write failing tests**

Create `tests/test_speakers/__init__.py` (empty file).

Create `tests/test_speakers/test_enrollment.py`:

```python
import shutil
from pathlib import Path

import pytest
import tomli_w

from whotalksitron.speakers.enrollment import (
    SpeakerStore,
    enroll_speaker,
    import_speaker,
    list_speakers,
)


@pytest.fixture
def speaker_dir(tmp_path):
    return tmp_path / "speakers"


@pytest.fixture
def sample_audio(tmp_path) -> Path:
    audio = tmp_path / "sample.wav"
    # Minimal WAV header (44 bytes) + 16000 samples at 16kHz = 1 second
    # For testing, just a non-empty file is sufficient
    audio.write_bytes(b"\x00" * 32044)
    return audio


def test_enroll_creates_directory_structure(speaker_dir, sample_audio):
    store = SpeakerStore(speaker_dir)
    store.enroll("matt", "atp", sample_audio, compute_embedding=False)

    speaker_path = speaker_dir / "atp" / "matt"
    assert speaker_path.exists()
    assert (speaker_path / "samples").is_dir()
    assert (speaker_path / "meta.toml").exists()
    assert len(list((speaker_path / "samples").iterdir())) == 1


def test_enroll_multiple_samples(speaker_dir, sample_audio, tmp_path):
    store = SpeakerStore(speaker_dir)
    store.enroll("matt", "atp", sample_audio, compute_embedding=False)

    second_sample = tmp_path / "sample2.wav"
    second_sample.write_bytes(b"\x00" * 32044)
    store.enroll("matt", "atp", second_sample, compute_embedding=False)

    samples_dir = speaker_dir / "atp" / "matt" / "samples"
    assert len(list(samples_dir.iterdir())) == 2


def test_enroll_updates_meta(speaker_dir, sample_audio, tmp_path):
    store = SpeakerStore(speaker_dir)
    store.enroll("matt", "atp", sample_audio, compute_embedding=False)

    meta = store.get_meta("matt", "atp")
    assert meta["name"] == "matt"
    assert meta["podcast"] == "atp"
    assert meta["sample_count"] == 1

    second = tmp_path / "s2.wav"
    second.write_bytes(b"\x00" * 100)
    store.enroll("matt", "atp", second, compute_embedding=False)

    meta = store.get_meta("matt", "atp")
    assert meta["sample_count"] == 2


def test_list_speakers_empty(speaker_dir):
    store = SpeakerStore(speaker_dir)
    assert store.list_speakers() == {}
    assert store.list_speakers(podcast="atp") == {}


def test_list_speakers_by_podcast(speaker_dir, sample_audio, tmp_path):
    store = SpeakerStore(speaker_dir)
    store.enroll("matt", "atp", sample_audio, compute_embedding=False)

    second = tmp_path / "s2.wav"
    second.write_bytes(b"\x00" * 100)
    store.enroll("casey", "atp", second, compute_embedding=False)

    third = tmp_path / "s3.wav"
    third.write_bytes(b"\x00" * 100)
    store.enroll("gruber", "talkshow", third, compute_embedding=False)

    all_speakers = store.list_speakers()
    assert "atp" in all_speakers
    assert "talkshow" in all_speakers
    assert set(all_speakers["atp"]) == {"matt", "casey"}
    assert all_speakers["talkshow"] == ["gruber"]

    atp_only = store.list_speakers(podcast="atp")
    assert "atp" in atp_only
    assert "talkshow" not in atp_only


def test_import_speaker(speaker_dir, sample_audio):
    store = SpeakerStore(speaker_dir)
    store.enroll("matt", "atp", sample_audio, compute_embedding=False)

    store.import_speaker("matt", from_podcast="atp", to_podcast="talkshow")

    assert (speaker_dir / "talkshow" / "matt" / "samples").is_dir()
    assert (speaker_dir / "talkshow" / "matt" / "meta.toml").exists()
    # Original still exists
    assert (speaker_dir / "atp" / "matt" / "samples").is_dir()


def test_import_speaker_not_found(speaker_dir):
    store = SpeakerStore(speaker_dir)
    with pytest.raises(FileNotFoundError, match="matt"):
        store.import_speaker("matt", from_podcast="atp", to_podcast="talkshow")


def test_embedding_path(speaker_dir):
    store = SpeakerStore(speaker_dir)
    path = store.embedding_path("matt", "atp")
    assert path == speaker_dir / "atp" / "matt" / "embeddings" / "embedding.npy"


def test_get_sample_paths(speaker_dir, sample_audio, tmp_path):
    store = SpeakerStore(speaker_dir)
    store.enroll("matt", "atp", sample_audio, compute_embedding=False)

    second = tmp_path / "s2.wav"
    second.write_bytes(b"\x00" * 100)
    store.enroll("matt", "atp", second, compute_embedding=False)

    paths = store.get_sample_paths("matt", "atp")
    assert len(paths) == 2
    assert all(p.exists() for p in paths)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_speakers/test_enrollment.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement speaker enrollment**

Create `src/whotalksitron/speakers/__init__.py`:

```python
"""Speaker enrollment, embedding computation, and voiceprint matching."""
```

Create `src/whotalksitron/speakers/enrollment.py`:

```python
from __future__ import annotations

import logging
import shutil
import tomllib
from datetime import datetime, timezone
from pathlib import Path

import tomli_w

logger = logging.getLogger(__name__)


class SpeakerStore:
    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir

    def enroll(
        self,
        name: str,
        podcast: str,
        sample_path: Path,
        compute_embedding: bool = True,
    ) -> None:
        import uuid

        speaker_dir = self._speaker_dir(podcast, name)
        samples_dir = speaker_dir / "samples"
        samples_dir.mkdir(parents=True, exist_ok=True)

        uid = uuid.uuid4().hex[:12]
        dest = samples_dir / f"sample-{uid}{sample_path.suffix}"
        shutil.copy2(sample_path, dest)

        self._write_meta(name, podcast)

        if compute_embedding:
            self._update_embedding(name, podcast)

    def import_speaker(
        self, name: str, *, from_podcast: str, to_podcast: str
    ) -> None:
        src = self._speaker_dir(from_podcast, name)
        if not src.exists():
            raise FileNotFoundError(
                f"Speaker {name!r} not found in podcast {from_podcast!r}"
            )
        dest = self._speaker_dir(to_podcast, name)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)

        meta = self.get_meta(name, to_podcast)
        meta["podcast"] = to_podcast
        meta_path = dest / "meta.toml"
        with open(meta_path, "wb") as f:
            tomli_w.dump(meta, f)

    def list_speakers(
        self, *, podcast: str | None = None
    ) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        if not self._base.exists():
            return result

        podcasts = (
            [self._base / podcast] if podcast else list(self._base.iterdir())
        )
        for podcast_dir in podcasts:
            if not podcast_dir.is_dir():
                continue
            speakers = sorted(
                d.name for d in podcast_dir.iterdir() if d.is_dir()
            )
            if speakers:
                result[podcast_dir.name] = speakers
        return result

    def get_meta(self, name: str, podcast: str) -> dict:
        meta_path = self._speaker_dir(podcast, name) / "meta.toml"
        if not meta_path.exists():
            return {}
        with open(meta_path, "rb") as f:
            return tomllib.load(f)

    def get_sample_paths(self, name: str, podcast: str) -> list[Path]:
        samples_dir = self._speaker_dir(podcast, name) / "samples"
        if not samples_dir.exists():
            return []
        return sorted(samples_dir.iterdir())

    def embedding_path(self, name: str, podcast: str) -> Path:
        return self._speaker_dir(podcast, name) / "embeddings" / "embedding.npy"

    def rebuild_embeddings(self, name: str, podcast: str) -> None:
        self._update_embedding(name, podcast)

    def _update_embedding(self, name: str, podcast: str) -> None:
        from whotalksitron.speakers.embeddings import (
            average_embeddings,
            get_embedding_computer,
            save_embedding,
        )

        samples = self.get_sample_paths(name, podcast)
        if not samples:
            return

        try:
            computer = get_embedding_computer()
        except Exception:
            logger.warning(
                "No embedding model available. Enroll succeeded but "
                "embedding not computed. Install pyannote for voiceprint matching."
            )
            return

        embeddings = []
        for sample in samples:
            try:
                emb = computer.compute(sample)
                embeddings.append(emb)
            except Exception:
                logger.warning("Failed to compute embedding for %s", sample)

        if embeddings:
            avg = average_embeddings(embeddings)
            emb_path = self.embedding_path(name, podcast)
            save_embedding(avg, emb_path)
            logger.info(
                "Embedding updated for %s/%s from %d samples",
                podcast, name, len(embeddings),
            )

    def _speaker_dir(self, podcast: str, name: str) -> Path:
        return self._base / podcast / name

    def _write_meta(self, name: str, podcast: str) -> None:
        speaker_dir = self._speaker_dir(podcast, name)
        samples_dir = speaker_dir / "samples"
        sample_count = len(list(samples_dir.iterdir())) if samples_dir.exists() else 0

        meta = {
            "name": name,
            "podcast": podcast,
            "sample_count": sample_count,
            "enrolled_at": datetime.now(timezone.utc).isoformat(),
        }
        meta_path = speaker_dir / "meta.toml"
        with open(meta_path, "wb") as f:
            tomli_w.dump(meta, f)


# Module-level convenience functions that create a SpeakerStore
# with the default config dir. Used by CLI commands.

def enroll_speaker(
    name: str, podcast: str, sample_path: Path, speakers_dir: Path
) -> None:
    store = SpeakerStore(speakers_dir)
    store.enroll(name, podcast, sample_path)


def import_speaker(
    name: str, from_podcast: str, to_podcast: str, speakers_dir: Path
) -> None:
    store = SpeakerStore(speakers_dir)
    store.import_speaker(name, from_podcast=from_podcast, to_podcast=to_podcast)


def list_speakers(
    speakers_dir: Path, podcast: str | None = None
) -> dict[str, list[str]]:
    store = SpeakerStore(speakers_dir)
    return store.list_speakers(podcast=podcast)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_speakers/test_enrollment.py -v`
Expected: all 8 tests PASS

- [ ] **Step 5: Commit** `[COMMIT]`

```bash
git add src/whotalksitron/speakers/ tests/test_speakers/
git commit -m "Add speaker enrollment and storage

SpeakerStore manages per-podcast speaker directories with audio
samples and TOML metadata. Supports enroll, import, and list."
```

---

### Task 10: Embedding computation `[sonnet]`

**Files:**
- Create: `src/whotalksitron/speakers/embeddings.py`
- Create: `tests/test_speakers/test_embeddings.py`

**Reference:** Read `docs/superpowers/specs/2026-04-18-whotalksitron-design/speakers.md` for embedding model choices (pyannote primary, ONNX fallback).

- [ ] **Step 1: Write failing tests**

Create `tests/test_speakers/test_embeddings.py`:

```python
import numpy as np
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from whotalksitron.speakers.embeddings import (
    EmbeddingComputer,
    get_embedding_computer,
    load_embedding,
    save_embedding,
    average_embeddings,
)


def test_save_and_load_embedding(tmp_path):
    embedding = np.random.randn(256).astype(np.float32)
    path = tmp_path / "embedding.npy"
    save_embedding(embedding, path)
    loaded = load_embedding(path)
    np.testing.assert_array_almost_equal(embedding, loaded)


def test_load_embedding_missing():
    result = load_embedding(Path("/nonexistent/embedding.npy"))
    assert result is None


def test_average_embeddings_single():
    e = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    result = average_embeddings([e])
    np.testing.assert_array_equal(result, e)


def test_average_embeddings_multiple():
    e1 = np.array([1.0, 0.0], dtype=np.float32)
    e2 = np.array([0.0, 1.0], dtype=np.float32)
    result = average_embeddings([e1, e2])
    expected = np.array([0.5, 0.5], dtype=np.float32)
    np.testing.assert_array_almost_equal(result, expected)


def test_average_embeddings_normalizes():
    e1 = np.array([3.0, 0.0], dtype=np.float32)
    e2 = np.array([3.0, 0.0], dtype=np.float32)
    result = average_embeddings([e1, e2])
    norm = np.linalg.norm(result)
    assert abs(norm - 1.0) < 1e-6


def test_average_embeddings_empty():
    with pytest.raises(ValueError, match="at least one"):
        average_embeddings([])


def test_embedding_computer_protocol():
    # EmbeddingComputer is a Protocol — verify concrete implementations satisfy it
    from whotalksitron.speakers.embeddings import _OnnxEmbedder
    computer = _OnnxEmbedder()
    assert isinstance(computer, EmbeddingComputer)
    assert hasattr(computer, "compute")
    assert hasattr(computer, "is_available")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_speakers/test_embeddings.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement embedding module**

Create `src/whotalksitron/speakers/embeddings.py`:

```python
from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

import numpy as np

logger = logging.getLogger(__name__)


class EmbeddingComputer(Protocol):
    def compute(self, audio_path: Path) -> np.ndarray: ...
    def is_available(self) -> bool: ...


def save_embedding(embedding: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, embedding)


def load_embedding(path: Path) -> np.ndarray | None:
    if not path.exists():
        return None
    return np.load(path)


def average_embeddings(embeddings: list[np.ndarray]) -> np.ndarray:
    if not embeddings:
        raise ValueError("Need at least one embedding to average")
    avg = np.mean(embeddings, axis=0)
    norm = np.linalg.norm(avg)
    if norm > 0:
        avg = avg / norm
    return avg.astype(np.float32)


def get_embedding_computer() -> EmbeddingComputer:
    try:
        return _PyAnnoteEmbedder()
    except ImportError:
        logger.info("pyannote not available, using ONNX fallback")
        return _OnnxEmbedder()


class _PyAnnoteEmbedder:
    def __init__(self) -> None:
        from pyannote.audio import Model, Inference
        self._model = Model.from_pretrained("pyannote/wespeaker-voxceleb-resnet34-LM")
        self._inference = Inference(self._model, window="whole")

    def compute(self, audio_path: Path) -> np.ndarray:
        embedding = self._inference(str(audio_path))
        return np.array(embedding).flatten().astype(np.float32)

    def is_available(self) -> bool:
        return True


class _OnnxEmbedder:
    def __init__(self) -> None:
        # ONNX fallback is a future enhancement.
        # For now, raise if pyannote is not available.
        pass

    def compute(self, audio_path: Path) -> np.ndarray:
        raise NotImplementedError(
            "ONNX embedding fallback is not yet implemented. "
            "Install pyannote: uv tool install whotalksitron --with local"
        )

    def is_available(self) -> bool:
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_speakers/test_embeddings.py -v`
Expected: all 7 tests PASS

- [ ] **Step 5: Commit** `[COMMIT]`

```bash
git add src/whotalksitron/speakers/embeddings.py tests/test_speakers/test_embeddings.py
git commit -m "Add embedding computation module

Save/load numpy embeddings, L2-normalized averaging, EmbeddingComputer
protocol with pyannote primary and ONNX fallback (stub)."
```

---

### Task 11: Voiceprint matching `[sonnet]`

**Files:**
- Create: `src/whotalksitron/speakers/matching.py`
- Create: `tests/test_speakers/test_matching.py`

**Reference:** Read `docs/superpowers/specs/2026-04-18-whotalksitron-design/speakers.md` for matching behavior (cosine similarity, threshold, relabeling).

- [ ] **Step 1: Write failing tests**

Create `tests/test_speakers/test_matching.py`:

```python
import numpy as np
import pytest

from whotalksitron.models import TranscriptResult, TranscriptSegment
from whotalksitron.speakers.matching import (
    cosine_similarity,
    match_speakers,
    SpeakerEmbeddings,
)


def test_cosine_similarity_identical():
    v = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    assert abs(cosine_similarity(v, v) - 1.0) < 1e-6


def test_cosine_similarity_orthogonal():
    a = np.array([1.0, 0.0], dtype=np.float32)
    b = np.array([0.0, 1.0], dtype=np.float32)
    assert abs(cosine_similarity(a, b)) < 1e-6


def test_cosine_similarity_opposite():
    a = np.array([1.0, 0.0], dtype=np.float32)
    b = np.array([-1.0, 0.0], dtype=np.float32)
    assert abs(cosine_similarity(a, b) + 1.0) < 1e-6


def test_match_speakers_relabels():
    segments = [
        TranscriptSegment(start=0.0, end=5.0, text="Hello", speaker="Speaker 01"),
        TranscriptSegment(start=5.0, end=10.0, text="World", speaker="Speaker 02"),
    ]
    result = TranscriptResult(segments=segments, metadata={})

    # Speaker 01's embedding is similar to matt's
    matt_emb = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    speaker_embeddings = SpeakerEmbeddings(
        enrolled={"matt": matt_emb},
        detected={"Speaker 01": np.array([0.95, 0.1, 0.0], dtype=np.float32)},
    )

    matched = match_speakers(result, speaker_embeddings, threshold=0.7)
    assert matched.segments[0].speaker == "matt"
    assert matched.segments[1].speaker == "Speaker 02"  # no match, unchanged


def test_match_speakers_no_detected():
    segments = [
        TranscriptSegment(start=0.0, end=5.0, text="Hello", speaker="Speaker 01"),
    ]
    result = TranscriptResult(segments=segments, metadata={})

    speaker_embeddings = SpeakerEmbeddings(
        enrolled={"matt": np.array([1.0, 0.0], dtype=np.float32)},
        detected={},
    )

    matched = match_speakers(result, speaker_embeddings, threshold=0.7)
    assert matched.segments[0].speaker == "Speaker 01"  # unchanged


def test_match_speakers_below_threshold():
    segments = [
        TranscriptSegment(start=0.0, end=5.0, text="Hello", speaker="Speaker 01"),
    ]
    result = TranscriptResult(segments=segments, metadata={})

    speaker_embeddings = SpeakerEmbeddings(
        enrolled={"matt": np.array([1.0, 0.0], dtype=np.float32)},
        detected={"Speaker 01": np.array([0.0, 1.0], dtype=np.float32)},
    )

    matched = match_speakers(result, speaker_embeddings, threshold=0.7)
    assert matched.segments[0].speaker == "Speaker 01"  # no match


def test_match_speakers_none_speaker_unchanged():
    segments = [
        TranscriptSegment(start=0.0, end=5.0, text="Hello"),
    ]
    result = TranscriptResult(segments=segments, metadata={})

    speaker_embeddings = SpeakerEmbeddings(
        enrolled={"matt": np.array([1.0, 0.0], dtype=np.float32)},
        detected={},
    )

    matched = match_speakers(result, speaker_embeddings, threshold=0.7)
    assert matched.segments[0].speaker is None


def test_match_speakers_at_exact_threshold():
    # Cosine similarity of exactly 0.7 should NOT match (threshold is exclusive)
    a = np.array([1.0, 0.0], dtype=np.float32)
    # Construct a vector with cosine similarity ~0.7 to a
    # cos(theta) = 0.7 => theta = acos(0.7)
    import math
    theta = math.acos(0.7)
    b = np.array([math.cos(theta), math.sin(theta)], dtype=np.float32)

    segments = [
        TranscriptSegment(start=0.0, end=5.0, text="Hello", speaker="Speaker 01"),
    ]
    result = TranscriptResult(segments=segments, metadata={})

    speaker_embeddings = SpeakerEmbeddings(
        enrolled={"matt": a},
        detected={"Speaker 01": b},
    )

    # At threshold=0.7, similarity of exactly 0.7 should not match (> not >=)
    matched = match_speakers(result, speaker_embeddings, threshold=0.7)
    assert matched.segments[0].speaker == "Speaker 01"

    # Just above threshold should match
    matched = match_speakers(result, speaker_embeddings, threshold=0.69)
    assert matched.segments[0].speaker == "matt"


def test_match_speakers_named_speaker_unchanged():
    segments = [
        TranscriptSegment(start=0.0, end=5.0, text="Hello", speaker="Matt"),
    ]
    result = TranscriptResult(segments=segments, metadata={})

    matched = match_speakers(
        result,
        SpeakerEmbeddings(enrolled={}, detected={}),
        threshold=0.7,
    )
    assert matched.segments[0].speaker == "Matt"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_speakers/test_matching.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement voiceprint matching**

Create `src/whotalksitron/speakers/matching.py`:

```python
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import numpy as np

from whotalksitron.models import TranscriptResult, TranscriptSegment

logger = logging.getLogger(__name__)

_GENERIC_PATTERN = re.compile(r"^Speaker \d{2,}$")


@dataclass
class SpeakerEmbeddings:
    enrolled: dict[str, np.ndarray] = field(default_factory=dict)
    detected: dict[str, np.ndarray] = field(default_factory=dict)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def match_speakers(
    result: TranscriptResult,
    speaker_embeddings: SpeakerEmbeddings,
    threshold: float,
) -> TranscriptResult:
    if not speaker_embeddings.enrolled or not speaker_embeddings.detected:
        return result

    label_map: dict[str, str] = {}
    for detected_name, detected_emb in speaker_embeddings.detected.items():
        best_name: str | None = None
        best_score = threshold

        for enrolled_name, enrolled_emb in speaker_embeddings.enrolled.items():
            score = cosine_similarity(detected_emb, enrolled_emb)
            logger.debug(
                "Similarity %s <-> %s: %.3f",
                detected_name, enrolled_name, score,
            )
            if score > best_score:
                best_score = score
                best_name = enrolled_name

        if best_name:
            label_map[detected_name] = best_name
            logger.info(
                "Matched %s -> %s (score: %.3f)",
                detected_name, best_name, best_score,
            )

    if not label_map:
        return result

    new_segments = []
    for seg in result.segments:
        speaker = seg.speaker
        if speaker and _GENERIC_PATTERN.match(speaker) and speaker in label_map:
            speaker = label_map[speaker]
        new_segments.append(TranscriptSegment(
            start=seg.start,
            end=seg.end,
            text=seg.text,
            speaker=speaker,
        ))

    return TranscriptResult(segments=new_segments, metadata=result.metadata)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_speakers/test_matching.py -v`
Expected: all 7 tests PASS

- [ ] **Step 5: Run full suite and commit** `[COMMIT]`

Run: `just test`
Expected: all tests pass

```bash
git add src/whotalksitron/speakers/matching.py tests/test_speakers/test_matching.py
git commit -m "Add voiceprint matching

Cosine similarity matching of detected speaker embeddings against
enrolled voiceprints. Relabels generic 'Speaker N' labels above
the configured threshold."
```

`[REVIEW:normal]` — Phase 4 complete. Speaker system handles file storage and user data.
