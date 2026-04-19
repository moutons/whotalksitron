from pathlib import Path

import pytest
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
