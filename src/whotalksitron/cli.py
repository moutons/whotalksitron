from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import click

from whotalksitron import __version__
from whotalksitron.config import Config, load_config
from whotalksitron.progress import ProgressReporter


def _setup_logging(level: str, fmt: str) -> None:
    numeric = getattr(logging, level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stderr)
    if fmt == "json":
        import json

        class JsonFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                return json.dumps(
                    {
                        "level": record.levelname,
                        "logger": record.name,
                        "message": record.getMessage(),
                    }
                )

        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    logging.root.handlers.clear()
    logging.root.addHandler(handler)
    logging.root.setLevel(numeric)


@click.group()
@click.version_option(version=__version__)
@click.option(
    "--log-level", default=None, type=click.Choice(["debug", "info", "warn", "error"])
)
@click.option("--log-format", default=None, type=click.Choice(["text", "json"]))
@click.option("--progress", is_flag=True, default=False)
@click.option("--quiet", "-q", is_flag=True, default=False)
@click.pass_context
def main(ctx: click.Context, log_level, log_format, progress, quiet) -> None:
    """Audio transcription CLI with speaker identification."""
    ctx.ensure_object(dict)
    ctx.obj["cli_overrides"] = {}
    if log_level:
        ctx.obj["cli_overrides"]["log_level"] = log_level
    if log_format:
        ctx.obj["cli_overrides"]["log_format"] = log_format

    config_path = os.environ.get("WHOTALKSITRON_CONFIG")
    cfg = load_config(
        config_path=Path(config_path) if config_path else None,
        cli_overrides=ctx.obj["cli_overrides"],
    )

    effective_level = log_level or cfg.log_level
    effective_format = log_format or cfg.log_format
    _setup_logging(effective_level, effective_format)

    ctx.obj["config"] = cfg
    ctx.obj["progress"] = progress or cfg.progress
    ctx.obj["quiet"] = quiet


@main.command()
@click.argument("audio_file", type=click.Path(exists=True, path_type=Path))
@click.option("--backend", type=click.Choice(["gemini", "pyannote", "whisper"]))
@click.option("--podcast", default=None)
@click.option("--output", "-o", default=None, type=click.Path(path_type=Path))
@click.option("--model", default=None)
@click.option("--identify-speakers", is_flag=True, default=False)
@click.pass_context
def transcribe(ctx, audio_file, backend, podcast, output, model, identify_speakers):
    """Transcribe an audio file to markdown."""
    cfg: Config = ctx.obj["config"]

    if backend:
        cfg.backend = backend
    if model:
        cfg.gemini_model = model
        cfg.whisper_model = model

    from whotalksitron.backends import BackendUnavailableError, select_backend
    from whotalksitron.models import SpeakerPool
    from whotalksitron.pipeline import Pipeline, PreprocessingError, ValidationError
    from whotalksitron.speakers.enrollment import SpeakerStore

    progress = ProgressReporter(enabled=ctx.obj["progress"])

    try:
        selected = select_backend(cfg)
    except BackendUnavailableError as e:
        click.echo(str(e), err=True)
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

    if output is None:
        output = audio_file.with_suffix(".md")

    pipeline = Pipeline(cfg)
    try:
        result = pipeline.run(
            audio_path=audio_file,
            output_path=output,
            backend=selected,
            podcast=podcast,
            speakers=speakers,
            progress=progress,
        )
    except (ValidationError, PreprocessingError) as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)
        return

    if not ctx.obj["quiet"]:
        click.echo(f"Wrote {output}")
        if result.warnings:
            for w in result.warnings:
                click.echo(f"Warning: {w}", err=True)

    ctx.exit(result.exit_code)


@main.command()
@click.option("--name", required=True)
@click.option("--podcast", required=True)
@click.option("--sample", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--rebuild", is_flag=True, default=False)
@click.pass_context
def enroll(ctx, name, podcast, sample, rebuild):
    """Enroll a speaker voice sample."""
    from whotalksitron.speakers.enrollment import SpeakerStore

    store = SpeakerStore(_speakers_dir())

    if rebuild:
        click.echo(f"Rebuilding embeddings for {name!r} in {podcast!r}...")
        store.rebuild_embeddings(name, podcast)
        click.echo("Rebuild complete.")
        return

    store.enroll(name, podcast, sample)
    meta = store.get_meta(name, podcast)
    count = meta.get("sample_count", 1)
    click.echo(f'Enrolled "{name}" for podcast "{podcast}" ({count} samples)')


@main.command("import-speaker")
@click.option("--name", required=True)
@click.option("--from", "from_podcast", required=True)
@click.option("--to", "to_podcast", required=True)
@click.pass_context
def import_speaker_cmd(ctx, name, from_podcast, to_podcast):
    """Import a speaker from one podcast to another."""
    from whotalksitron.speakers.enrollment import SpeakerStore

    store = SpeakerStore(_speakers_dir())
    try:
        store.import_speaker(name, from_podcast=from_podcast, to_podcast=to_podcast)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)
        return

    click.echo(f'Imported "{name}" from "{from_podcast}" to "{to_podcast}"')


@main.command("list-speakers")
@click.option("--podcast", default=None)
@click.pass_context
def list_speakers_cmd(ctx, podcast):
    """List enrolled speakers."""
    from whotalksitron.speakers.enrollment import SpeakerStore

    store = SpeakerStore(_speakers_dir())
    speakers = store.list_speakers(podcast=podcast)

    if not speakers:
        click.echo("No speakers enrolled.")
        return

    for pod, names in sorted(speakers.items()):
        click.echo(f"{pod}:")
        for name in names:
            meta = store.get_meta(name, pod)
            count = meta.get("sample_count", 0)
            click.echo(f"  {name} ({count} samples)")


@main.command()
@click.option("--show", is_flag=True, default=False)
@click.option("--set", "set_value", default=None)
@click.option("--init", "init_config", is_flag=True, default=False)
@click.pass_context
def config(ctx, show, set_value, init_config):
    """Manage configuration."""
    cfg: Config = ctx.obj["config"]

    if init_config:
        config_path = _config_path()
        if config_path.exists():
            click.echo(f"Config already exists: {config_path}", err=True)
            ctx.exit(1)
            return
        cfg.write_default(config_path)
        click.echo(f"Created {config_path}")
        return

    if show:
        click.echo(cfg.show())
        return

    if set_value:
        config_path = _config_path()
        if not config_path.exists():
            click.echo(
                "No config file. Run `whotalksitron config --init` first.", err=True
            )
            ctx.exit(1)
            return

        key, _, value = set_value.partition("=")
        if not value:
            click.echo("Invalid format. Use: --set key=value", err=True)
            ctx.exit(2)
            return

        import tomllib

        with open(config_path, "rb") as f:
            data = tomllib.load(f)

        parts = key.split(".")
        target = data
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = _coerce_value(value)

        import tomli_w

        with open(config_path, "wb") as f:
            tomli_w.dump(data, f)
        click.echo(f"Set {key} = {value}")
        return

    click.echo("Use --show, --set, or --init. Run --help for details.")


@main.command("extract-samples")
@click.argument("audio_file", type=click.Path(exists=True, path_type=Path))
@click.option("--podcast", default=None)
@click.option("--output", "-o", default=None, type=click.Path(path_type=Path))
@click.pass_context
def extract_samples_cmd(ctx, audio_file, podcast, output):
    """Extract speaker voice samples from an audio file."""
    cfg: Config = ctx.obj["config"]

    from whotalksitron.backends import BackendUnavailableError, select_backend
    from whotalksitron.models import SpeakerPool
    from whotalksitron.pipeline import Pipeline, PreprocessingError, ValidationError
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
        audio_file,
        result.transcript.segments,
        output_dir,
    )

    click.echo(f"\nExtracted samples to {output_dir}/:")
    for speaker, paths in sorted(extracted.items()):
        matched = "matched" if not speaker.startswith("Speaker") else "unmatched"
        click.echo(f"  {speaker}/  {len(paths)} clips  ({matched})")

    unmatched = [s for s in extracted if s.startswith("Speaker")]
    if unmatched and podcast:
        click.echo("\nTo enroll unmatched speakers:")
        for speaker in unmatched:
            safe = speaker.lower().replace(" ", "-")
            click.echo(
                f"  whotalksitron enroll --name NAME --podcast {podcast} "
                f"--sample {output_dir}/{safe}/sample-001.wav"
            )


def _speakers_dir() -> Path:
    env = os.environ.get("WHOTALKSITRON_SPEAKERS_DIR")
    if env:
        return Path(env)
    return Path.home() / ".config" / "whotalksitron" / "speakers"


def _config_path() -> Path:
    env = os.environ.get("WHOTALKSITRON_CONFIG")
    if env:
        return Path(env)
    return Path.home() / ".config" / "whotalksitron" / "config.toml"


def _coerce_value(value: str) -> object:
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


if __name__ == "__main__":
    main()
