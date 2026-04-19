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
    diarization = [
        (0.0, 7.0, "SPEAKER_00"),
        (7.0, 15.0, "SPEAKER_01"),
    ]

    merged = _merge_transcription_and_diarization(transcription, diarization)
    assert len(merged) == 3
    assert merged[0].speaker == "Speaker 01"
    assert (
        merged[1].speaker == "Speaker 02"
    )  # majority overlap with SPEAKER_01 (3s vs 2s)
    assert merged[2].speaker == "Speaker 02"


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


def test_select_device_auto():
    device = _select_device("auto")
    assert device in ("cpu", "cuda", "mps")


def test_select_device_explicit():
    assert _select_device("cpu") == "cpu"
