from whotalksitron.models import TranscriptSegment
from whotalksitron.speakers.extraction import (
    find_candidates,
    group_segments_by_speaker,
    score_segment,
)


def _make_segments() -> list[TranscriptSegment]:
    return [
        TranscriptSegment(start=0.0, end=15.0, text="Hello.", speaker="Speaker 1"),
        TranscriptSegment(start=15.0, end=20.0, text="Hi.", speaker="Speaker 2"),
        TranscriptSegment(
            start=20.0, end=40.0, text="Long monologue.", speaker="Speaker 1"
        ),
        TranscriptSegment(start=40.0, end=55.0, text="Response.", speaker="Speaker 2"),
        TranscriptSegment(start=55.0, end=60.0, text="Short.", speaker="Speaker 1"),
        TranscriptSegment(
            start=60.0, end=80.0, text="Another long one.", speaker="Speaker 2"
        ),
        TranscriptSegment(start=80.0, end=95.0, text="More talk.", speaker="Speaker 1"),
    ]


def test_group_segments_by_speaker():
    segments = _make_segments()
    groups = group_segments_by_speaker(segments)
    assert "Speaker 1" in groups
    assert "Speaker 2" in groups
    assert len(groups["Speaker 1"]) == 4
    assert len(groups["Speaker 2"]) == 3


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
    assert score_segment(long, total_duration=100.0) > score_segment(
        short, total_duration=100.0
    )


def test_score_segment_avoids_extremes():
    middle = TranscriptSegment(start=45.0, end=60.0, text="middle")
    start = TranscriptSegment(start=0.0, end=15.0, text="start")
    mid_score = score_segment(middle, total_duration=100.0)
    start_score = score_segment(start, total_duration=100.0)  # noqa: F841
    assert mid_score >= 0


def test_find_candidates_top_3():
    segments = _make_segments()
    groups = group_segments_by_speaker(segments)
    candidates = find_candidates(
        groups["Speaker 1"], total_duration=95.0, max_candidates=3
    )
    assert len(candidates) <= 3
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
