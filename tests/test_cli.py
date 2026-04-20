import gzip
import json
import logging
from pathlib import Path

import pytest
from click.testing import CliRunner

from whotalksitron.cli import main


def test_invocation_logged_to_file(tmp_path):
    log_file = tmp_path / "test.log"
    config_file = tmp_path / "config.toml"
    import tomli_w

    data = {"logging": {"file": str(log_file)}}
    config_file.write_bytes(tomli_w.dumps(data).encode())

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--log-level", "info", "config", "--show"],
        env={"WHOTALKSITRON_CONFIG": str(config_file)},
    )
    assert result.exit_code == 0

    lines = log_file.read_text().strip().split("\n")
    records = [json.loads(line) for line in lines if line.strip()]
    invocations = [r for r in records if r.get("message") == "invocation"]
    assert len(invocations) == 1
    assert "argv" in invocations[0]
    assert "version" in invocations[0]


def test_invocation_sanitizes_secrets(tmp_path):
    log_file = tmp_path / "test.log"
    config_file = tmp_path / "config.toml"
    import tomli_w

    data = {"logging": {"file": str(log_file)}}
    config_file.write_bytes(tomli_w.dumps(data).encode())

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["config", "--show"],
        env={"WHOTALKSITRON_CONFIG": str(config_file)},
    )
    assert result.exit_code == 0

    # Verify sanitization function works directly
    from whotalksitron.cli import _sanitize_argv

    argv = ["transcribe", "--api-key", "secret123", "--backend", "gemini"]
    sanitized = _sanitize_argv(argv)
    assert sanitized == ["transcribe", "--api-key", "***", "--backend", "gemini"]


def test_sanitize_argv_no_secrets():
    from whotalksitron.cli import _sanitize_argv

    argv = ["transcribe", "--backend", "gemini", "episode.mp3"]
    assert _sanitize_argv(argv) == argv


def test_sanitize_argv_multiple_secrets():
    from whotalksitron.cli import _sanitize_argv

    argv = ["--api-key", "s1", "--token", "s2", "--password", "s3", "file.mp3"]
    sanitized = _sanitize_argv(argv)
    assert sanitized == [
        "--api-key",
        "***",
        "--token",
        "***",
        "--password",
        "***",
        "file.mp3",
    ]


def test_sanitize_argv_equals_form():
    from whotalksitron.cli import _sanitize_argv

    argv = ["--api-key=secret123", "--backend", "gemini"]
    sanitized = _sanitize_argv(argv)
    assert sanitized[0] == "--api-key=***"


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def fake_audio(tmp_path) -> Path:
    audio = tmp_path / "episode.mp3"
    audio.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 1000)
    return audio


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
    result = runner.invoke(
        main,
        ["config", "--init"],
        env={
            "WHOTALKSITRON_CONFIG": str(config_file),
        },
    )
    assert result.exit_code == 0
    assert config_file.exists()


def test_config_show(runner, tmp_path):
    config_file = tmp_path / "config.toml"
    runner.invoke(
        main,
        ["config", "--init"],
        env={
            "WHOTALKSITRON_CONFIG": str(config_file),
        },
    )
    result = runner.invoke(
        main,
        ["config", "--show"],
        env={
            "WHOTALKSITRON_CONFIG": str(config_file),
        },
    )
    assert result.exit_code == 0
    assert "backend" in result.output


def test_enroll_creates_speaker(runner, tmp_path, fake_audio):
    speakers_dir = tmp_path / "speakers"
    result = runner.invoke(
        main,
        [
            "enroll",
            "--name",
            "matt",
            "--podcast",
            "atp",
            "--sample",
            str(fake_audio),
        ],
        env={"WHOTALKSITRON_SPEAKERS_DIR": str(speakers_dir)},
    )
    assert result.exit_code == 0
    assert (speakers_dir / "atp" / "matt" / "samples").exists()


def test_list_speakers_empty(runner, tmp_path):
    speakers_dir = tmp_path / "speakers"
    result = runner.invoke(
        main,
        ["list-speakers"],
        env={
            "WHOTALKSITRON_SPEAKERS_DIR": str(speakers_dir),
        },
    )
    assert result.exit_code == 0
    assert "No speakers enrolled" in result.output


def test_config_set(runner, tmp_path):
    config_file = tmp_path / "config.toml"
    runner.invoke(
        main,
        ["config", "--init"],
        env={
            "WHOTALKSITRON_CONFIG": str(config_file),
        },
    )
    result = runner.invoke(
        main,
        ["config", "--set", "gemini.model=gemini-2.5-pro"],
        env={
            "WHOTALKSITRON_CONFIG": str(config_file),
        },
    )
    assert result.exit_code == 0
    assert "Set gemini.model" in result.output

    import tomllib

    with open(config_file, "rb") as f:
        data = tomllib.load(f)
    assert data["gemini"]["model"] == "gemini-2.5-pro"


def test_config_init_includes_logging(runner, tmp_path):
    config_file = tmp_path / "config.toml"
    result = runner.invoke(
        main,
        ["config", "--init"],
        env={"WHOTALKSITRON_CONFIG": str(config_file)},
    )
    assert result.exit_code == 0

    import tomllib

    with open(config_file, "rb") as f:
        data = tomllib.load(f)
    assert "logging" in data
    assert "file" in data["logging"]
    assert "file_max_bytes" in data["logging"]
    assert "file_backup_count" in data["logging"]


def test_transcribe_identify_speakers_flag(runner):
    result = runner.invoke(main, ["transcribe", "--help"])
    assert "--identify-speakers" in result.output


def test_global_flags(runner):
    result = runner.invoke(main, ["--log-level", "debug", "--help"])
    assert result.exit_code == 0


def test_extract_samples_help(runner):
    result = runner.invoke(main, ["extract-samples", "--help"])
    assert result.exit_code == 0
    assert "--podcast" in result.output
    assert "--output" in result.output


def test_file_handler_writes_json(tmp_path):
    from whotalksitron.cli import _setup_file_logging

    log_file = tmp_path / "test.log"
    handler = _setup_file_logging(str(log_file), max_bytes=1_048_576, backup_count=3)
    assert handler is not None

    try:
        test_logger = logging.getLogger("test.file_handler")
        test_logger.setLevel(logging.DEBUG)
        test_logger.addHandler(handler)
        test_logger.debug("hello from test")
        handler.flush()

        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["level"] == "DEBUG"
        assert record["logger"] == "test.file_handler"
        assert record["message"] == "hello from test"
        assert "ts" in record
    finally:
        test_logger.removeHandler(handler)
        handler.close()


def test_file_handler_returns_none_on_bad_path():
    from whotalksitron.cli import _setup_file_logging

    handler = _setup_file_logging(
        "/no/such/dir/test.log", max_bytes=1_048_576, backup_count=3
    )
    assert handler is None


def test_file_handler_creates_parent_dir(tmp_path):
    from whotalksitron.cli import _setup_file_logging

    log_file = tmp_path / "subdir" / "nested" / "test.log"
    handler = _setup_file_logging(str(log_file), max_bytes=1_048_576, backup_count=3)
    assert handler is not None
    assert log_file.parent.exists()
    handler.close()


def test_file_handler_gzip_rotation(tmp_path):
    from whotalksitron.cli import _setup_file_logging

    log_file = tmp_path / "test.log"
    # Small max_bytes to trigger rotation
    handler = _setup_file_logging(str(log_file), max_bytes=200, backup_count=2)
    assert handler is not None

    try:
        test_logger = logging.getLogger("test.rotation")
        test_logger.setLevel(logging.DEBUG)
        test_logger.addHandler(handler)

        for i in range(50):
            test_logger.debug("rotation test line %d with padding to fill bytes", i)

        handler.flush()

        backup = tmp_path / "test.log.1.gz"
        assert backup.exists(), f"Expected gzip backup at {backup}"
        content = gzip.decompress(backup.read_bytes()).decode()
        assert "rotation test line" in content
    finally:
        test_logger.removeHandler(handler)
        handler.close()


def test_file_handler_disabled_when_empty():
    from whotalksitron.cli import _setup_file_logging

    handler = _setup_file_logging("", max_bytes=1_048_576, backup_count=3)
    assert handler is None


def test_console_filter_passes_whotalksitron_loggers():
    """Console handler must pass whotalksitron.* log records."""
    from whotalksitron.cli import _setup_logging

    _setup_logging("info", "text")

    console = None
    for h in logging.root.handlers:
        if h.get_name() == "whotalksitron_console":
            console = h
            break
    assert console is not None

    record = logging.LogRecord(
        "whotalksitron.backends.gemini", logging.INFO, "", 0, "test msg", (), None
    )
    assert console.filter(record)


def test_console_filter_blocks_third_party_loggers():
    """Console handler must block httpx, google_genai, and other third-party loggers."""
    from whotalksitron.cli import _setup_logging

    _setup_logging("info", "text")

    console = None
    for h in logging.root.handlers:
        if h.get_name() == "whotalksitron_console":
            console = h
            break
    assert console is not None

    for name in ("httpx", "google_genai.models", "google.auth", "httpcore"):
        record = logging.LogRecord(name, logging.INFO, "", 0, "noise", (), None)
        assert not console.filter(record), f"Should block {name}"


def test_console_filter_blocks_third_party_even_at_debug():
    """Third-party loggers stay blocked even with --log-level debug."""
    from whotalksitron.cli import _setup_logging

    _setup_logging("debug", "text")

    console = None
    for h in logging.root.handlers:
        if h.get_name() == "whotalksitron_console":
            console = h
            break
    assert console is not None

    record = logging.LogRecord("httpx", logging.DEBUG, "", 0, "noise", (), None)
    assert not console.filter(record)


def test_invocation_not_shown_at_info_level(runner, tmp_path):
    """Invocation record must not appear on console at default info level."""
    config_file = tmp_path / "config.toml"
    import tomli_w

    data = {"logging": {"file": ""}}
    config_file.write_bytes(tomli_w.dumps(data).encode())

    result = runner.invoke(
        main,
        ["config", "--show"],
        env={"WHOTALKSITRON_CONFIG": str(config_file)},
    )
    assert result.exit_code == 0
    assert "invocation" not in result.output


def test_setup_logging_preserves_non_console_handlers():
    """_setup_logging must only replace the console handler, not clear all handlers."""
    import logging

    from whotalksitron.cli import _setup_logging

    # Add a dummy file-like handler
    dummy = logging.FileHandler("/dev/null")
    dummy.set_name("file_log")
    logging.root.addHandler(dummy)

    try:
        _setup_logging("info", "text")

        handler_names = [h.get_name() for h in logging.root.handlers]
        assert "file_log" in handler_names, "File handler was removed by _setup_logging"
        assert any(
            isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.FileHandler)
            for h in logging.root.handlers
        ), "Console handler not present"
    finally:
        logging.root.removeHandler(dummy)
        dummy.close()
