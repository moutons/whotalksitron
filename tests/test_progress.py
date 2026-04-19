import io
import json

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
