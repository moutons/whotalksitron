from whotalksitron.models import TranscriptResult, TranscriptSegment
from whotalksitron.output import render_transcript


def test_render_basic_transcript():
    result = TranscriptResult(
        segments=[
            TranscriptSegment(start=0.0, end=5.0, text="Hello world.", speaker="Matt"),
            TranscriptSegment(
                start=5.0, end=10.0, text="Hi there.", speaker="Speaker 02"
            ),
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
    assert "**[00:00:05] Speaker 02:** Hi there." in output


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
            TranscriptSegment(
                start=5.0, end=10.0, text="Unknown.", speaker="Speaker 01"
            ),
            TranscriptSegment(start=10.0, end=15.0, text="No label."),
        ],
        metadata={"model": "test", "backend": "test"},
    )
    output = render_transcript(result, source_file="test.mp3")
    assert "**[00:00:00] Matt:**" in output
    assert "**[00:00:05] Speaker 01:**" in output
    assert "**[00:00:10]**" in output
