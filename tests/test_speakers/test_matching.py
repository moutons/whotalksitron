import numpy as np

from whotalksitron.models import TranscriptResult, TranscriptSegment
from whotalksitron.speakers.matching import (
    SpeakerEmbeddings,
    cosine_similarity,
    match_speakers,
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
        TranscriptSegment(start=0.0, end=5.0, text="Hello", speaker="Speaker 1"),
        TranscriptSegment(start=5.0, end=10.0, text="World", speaker="Speaker 2"),
    ]
    result = TranscriptResult(segments=segments, metadata={})

    matt_emb = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    speaker_embeddings = SpeakerEmbeddings(
        enrolled={"matt": matt_emb},
        detected={"Speaker 1": np.array([0.95, 0.1, 0.0], dtype=np.float32)},
    )

    matched = match_speakers(result, speaker_embeddings, threshold=0.7)
    assert matched.segments[0].speaker == "matt"
    assert matched.segments[1].speaker == "Speaker 2"


def test_match_speakers_no_detected():
    segments = [
        TranscriptSegment(start=0.0, end=5.0, text="Hello", speaker="Speaker 1"),
    ]
    result = TranscriptResult(segments=segments, metadata={})

    speaker_embeddings = SpeakerEmbeddings(
        enrolled={"matt": np.array([1.0, 0.0], dtype=np.float32)},
        detected={},
    )

    matched = match_speakers(result, speaker_embeddings, threshold=0.7)
    assert matched.segments[0].speaker == "Speaker 1"


def test_match_speakers_below_threshold():
    segments = [
        TranscriptSegment(start=0.0, end=5.0, text="Hello", speaker="Speaker 1"),
    ]
    result = TranscriptResult(segments=segments, metadata={})

    speaker_embeddings = SpeakerEmbeddings(
        enrolled={"matt": np.array([1.0, 0.0], dtype=np.float32)},
        detected={"Speaker 1": np.array([0.0, 1.0], dtype=np.float32)},
    )

    matched = match_speakers(result, speaker_embeddings, threshold=0.7)
    assert matched.segments[0].speaker == "Speaker 1"


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
