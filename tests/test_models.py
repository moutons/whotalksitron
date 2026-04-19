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
        TranscriptSegment(start=15.0, end=20.0, text="d", speaker="Speaker 02"),
    ]
    result = TranscriptResult(segments=segments, metadata={})
    assert result.speakers == {"Matt", "Speaker 02"}
    assert result.unmatched_speakers == {"Speaker 02"}


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
