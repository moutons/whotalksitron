from __future__ import annotations

import logging
import os
import re
import sys
from datetime import UTC
from pathlib import Path

import click

from whotalksitron import __version__
from whotalksitron.config import Config, load_config
from whotalksitron.progress import ProgressReporter

logger = logging.getLogger(__name__)


_CONSOLE_HANDLER_NAME = "whotalksitron_console"


class _ConsoleFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.name.startswith("whotalksitron")


_SECRET_FLAG_PATTERN = re.compile(
    r"-{1,2}[a-z_-]*(key|token|secret|password)[a-z_-]*", re.IGNORECASE
)


def _sanitize_argv(argv: list[str]) -> list[str]:
    result = []
    redact_next = False
    for arg in argv:
        if redact_next:
            result.append("***")
            redact_next = False
            continue
        if "=" in arg:
            flag, _, _value = arg.partition("=")
            if _SECRET_FLAG_PATTERN.fullmatch(flag):
                result.append(f"{flag}=***")
                continue
        if _SECRET_FLAG_PATTERN.fullmatch(arg):
            result.append(arg)
            redact_next = True
            continue
        result.append(arg)
    return result


def _friendly_message(exc: Exception) -> str:
    # Walk cause chain for wrapped errors (RetryExhausted, etc.)
    from whotalksitron.retry import RetryExhausted

    if isinstance(exc, RetryExhausted) and exc.__cause__ is not None:
        return _friendly_message(exc.__cause__)

    # Gemini / Google Cloud errors
    try:
        from google.genai.errors import ClientError, ServerError

        if isinstance(exc, ClientError):
            code = getattr(exc, "code", 0) or 0
            if code == 401:
                return (
                    "Authentication failed. Check your API key or run: "
                    "gcloud auth application-default login"
                )
            if code == 404:
                return f"Model not found. Check gemini.model in your config. ({exc})"
            if code == 429:
                return "Rate limited by Gemini API. Wait a moment and try again."
            return f"Gemini API error ({code}): {exc}"
        if isinstance(exc, ServerError):
            code = getattr(exc, "code", 0) or 0
            return f"Gemini API server error ({code}). Try again later."
    except ImportError:
        pass

    try:
        from google.auth.exceptions import DefaultCredentialsError, RefreshError

        if isinstance(exc, DefaultCredentialsError):
            return (
                "No Google Cloud credentials found. Run: "
                "gcloud auth application-default login"
            )
        if isinstance(exc, RefreshError):
            return (
                "Google Cloud credentials expired. Run: "
                "gcloud auth application-default login"
            )
    except ImportError:
        pass

    # GCS errors
    try:
        from google.api_core.exceptions import GoogleAPIError

        if isinstance(exc, GoogleAPIError):
            return f"Google Cloud Storage error: {exc}"
    except ImportError:
        pass

    # httpx errors
    try:
        import httpx

        if isinstance(exc, httpx.ConnectError):
            url = ""
            req = getattr(exc, "request", None)
            if req is not None:
                url = str(getattr(req, "url", ""))
            if url:
                return f"Cannot connect to {url}. Check your network connection."
            return "Cannot connect to server. Check your network connection."
        if isinstance(exc, httpx.TimeoutException):
            return "Request timed out. Check your network connection and try again."
        if isinstance(exc, httpx.HTTPStatusError):
            url = ""
            req = getattr(exc, "request", None)
            if req is not None:
                url = str(getattr(req, "url", ""))
            code = getattr(getattr(exc, "response", None), "status_code", "?")
            if url:
                return f"HTTP {code} from {url}."
            return f"HTTP request failed with status {code}."
    except ImportError:
        pass

    if isinstance(exc, TimeoutError):
        return "Operation timed out. Check your network connection and try again."

    if isinstance(exc, ImportError):
        msg = str(exc)
        if "pyannote" in msg or "torch" in msg:
            return (
                "Pyannote backend requires extra dependencies. Install: "
                "uv tool install whotalksitron --with local"
            )
        return f"Missing dependency: {exc}"

    if isinstance(exc, RuntimeError):
        msg = str(exc)
        if any(kw in msg.lower() for kw in ("cuda", "torch", "pyannote")):
            return (
                f"Pyannote error: {msg}. "
                "Try --backend gemini or check device settings."
            )
        return msg

    if isinstance(exc, OSError):
        return str(exc)

    return f"Unexpected error: {exc}"


def _numeric_level(level: str) -> int:
    return getattr(logging, level.upper(), logging.INFO)


def _setup_logging(level: str, fmt: str) -> None:
    numeric = _numeric_level(level)

    # Remove only the console handler, preserve file and other handlers
    for h in logging.root.handlers[:]:
        if h.get_name() == _CONSOLE_HANDLER_NAME:
            logging.root.removeHandler(h)

    handler = logging.StreamHandler(sys.stderr)
    handler.set_name(_CONSOLE_HANDLER_NAME)
    handler.setLevel(numeric)  # console handler filters by level
    handler.addFilter(_ConsoleFilter())
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
        class _ConsoleFormatter(logging.Formatter):
            """Plain text formatter that suppresses tracebacks on console."""

            def format(self, record: logging.LogRecord) -> str:
                # Temporarily clear exc_info so the traceback is not emitted to console
                saved_exc_info = record.exc_info
                saved_exc_text = record.exc_text
                record.exc_info = None
                record.exc_text = None
                try:
                    return super().format(record)
                finally:
                    record.exc_info = saved_exc_info
                    record.exc_text = saved_exc_text

        handler.setFormatter(_ConsoleFormatter("%(levelname)s %(name)s: %(message)s"))
    logging.root.addHandler(handler)
    logging.root.setLevel(logging.DEBUG)  # root passes everything; handlers filter


_FILE_HANDLER_NAME = "whotalksitron_file"


def _setup_file_logging(
    log_file: str,
    max_bytes: int,
    backup_count: int,
) -> logging.Handler | None:
    if not log_file:
        return None

    import gzip
    import json
    import tempfile
    from datetime import datetime
    from logging.handlers import RotatingFileHandler

    log_path = Path(log_file)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(
            f"Warning: cannot create log directory {log_path.parent}: {e}",
            file=sys.stderr,
        )
        return None

    try:
        handler = RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
        )
    except OSError as e:
        print(f"Warning: cannot open log file {log_path}: {e}", file=sys.stderr)
        return None

    handler.set_name(_FILE_HANDLER_NAME)

    def _namer(name: str) -> str:
        return name + ".gz"

    def _rotator(source: str, dest: str) -> None:
        import contextlib

        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".gz", dir=str(log_path.parent))
        try:
            with (
                os.fdopen(tmp_fd, "wb") as tmp_f,
                gzip.GzipFile(fileobj=tmp_f, mode="wb") as gz,
                open(source, "rb") as src,
            ):
                while chunk := src.read(65536):
                    gz.write(chunk)
            os.replace(tmp_path, dest)
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise
        os.unlink(source)

    handler.namer = _namer
    handler.rotator = _rotator

    class FileJsonFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            try:
                data: dict[str, object] = {
                    "ts": datetime.fromtimestamp(record.created, tz=UTC).strftime(
                        "%Y-%m-%dT%H:%M:%S.%f"
                    )[:-3]
                    + "Z",
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                }
                if hasattr(record, "argv"):
                    data["argv"] = record.argv
                if hasattr(record, "version"):
                    data["version"] = record.version
                if record.exc_info:
                    import traceback as tb_mod

                    data["traceback"] = "".join(
                        tb_mod.format_exception(*record.exc_info)
                    )
                return json.dumps(data)
            except Exception:
                try:
                    return json.dumps(
                        {"level": record.levelname, "message": record.getMessage()}
                    )
                except Exception:
                    return '{"level":"UNKNOWN","message":"log formatting failed"}'

    handler.setFormatter(FileJsonFormatter())
    handler.setLevel(logging.DEBUG)

    import atexit
    import contextlib

    def _cleanup() -> None:
        with contextlib.suppress(Exception):
            handler.flush()
        with contextlib.suppress(Exception):
            logging.root.removeHandler(handler)
        with contextlib.suppress(Exception):
            handler.close()

    atexit.register(_cleanup)

    return handler


_GLOBAL_OPT_NAMES = ("log_level", "log_format", "progress", "quiet")

_global_options = [
    click.option(
        "--log-level",
        default=None,
        type=click.Choice(["debug", "info", "warn", "error"]),
    ),
    click.option("--log-format", default=None, type=click.Choice(["text", "json"])),
    click.option("--progress", is_flag=True, default=False),
    click.option("--quiet", "-q", is_flag=True, default=False),
]


def _apply_global_options(fn):
    for option in reversed(_global_options):
        fn = option(fn)
    return fn


def _init_context(ctx, log_level, log_format, progress, quiet):
    if ctx.obj.get("_initialized"):
        if log_level and log_level != ctx.obj.get("_log_level"):
            _setup_logging(log_level, log_format or "text")
        return
    ctx.obj["_initialized"] = True
    ctx.obj["_log_level"] = log_level
    ctx.obj["cli_overrides"] = {}
    if log_level:
        ctx.obj["cli_overrides"]["log_level"] = log_level
    if log_format:
        ctx.obj["cli_overrides"]["log_format"] = log_format

    early_level = log_level or "info"
    early_format = log_format or "text"
    _setup_logging(early_level, early_format)

    config_path = os.environ.get("WHOTALKSITRON_CONFIG")
    cfg = load_config(
        config_path=Path(config_path) if config_path else None,
        cli_overrides=ctx.obj["cli_overrides"],
    )

    effective_level = log_level or cfg.log_level
    effective_format = log_format or cfg.log_format
    if effective_level != early_level or effective_format != early_format:
        _setup_logging(effective_level, effective_format)

    ctx.obj["config"] = cfg
    ctx.obj["progress"] = progress or cfg.progress
    ctx.obj["quiet"] = quiet

    # Set up file logging (once per process)
    if not any(h.get_name() == _FILE_HANDLER_NAME for h in logging.root.handlers):
        file_handler = _setup_file_logging(
            cfg.log_file, cfg.log_file_max_bytes, cfg.log_file_backup_count
        )
        if file_handler:
            logging.root.addHandler(file_handler)

    # Log invocation record
    argv = sys.argv[1:] if len(sys.argv) > 1 else []
    record = logger.makeRecord(
        logger.name,
        logging.DEBUG,
        "",
        0,
        "invocation",
        (),
        None,
    )
    record.argv = _sanitize_argv(argv)
    record.version = __version__
    logger.handle(record)


def with_global_options(fn):
    import functools

    @_apply_global_options
    @click.pass_context
    @functools.wraps(fn)
    def wrapper(ctx, *args, **kwargs):
        ctx.ensure_object(dict)
        g = {k: kwargs.pop(k) for k in _GLOBAL_OPT_NAMES}
        _init_context(ctx, **g)
        return ctx.invoke(fn, **kwargs)

    return wrapper


@click.group()
@click.version_option(version=__version__)
@_apply_global_options
@click.pass_context
def main(ctx: click.Context, log_level, log_format, progress, quiet) -> None:
    """Audio transcription CLI with speaker identification."""
    ctx.ensure_object(dict)
    _init_context(ctx, log_level, log_format, progress, quiet)


@main.command()
@click.argument("audio_file", type=click.Path(exists=True, path_type=Path))
@click.option("--backend", type=click.Choice(["gemini", "pyannote", "whisper"]))
@click.option("--podcast", default=None)
@click.option("--output", "-o", default=None, type=click.Path(path_type=Path))
@click.option("--model", default=None)
@click.option("--identify-speakers", is_flag=True, default=False)
@click.option(
    "--overwrite",
    "-f",
    is_flag=True,
    default=False,
    help="Overwrite output file if it exists.",
)
@with_global_options
def transcribe(
    audio_file, backend, podcast, output, model, identify_speakers, overwrite
):
    """Transcribe an audio file to markdown."""
    ctx = click.get_current_context()
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
        output = audio_file.with_name(audio_file.stem + "-transcript.md")

    if output.exists() and not overwrite:
        click.echo(f"Output file already exists: {output}", err=True)
        click.echo(
            "Use --overwrite / -f to overwrite, "
            "or --output / -o to choose a different path.",
            err=True,
        )
        ctx.exit(1)
        return

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
@with_global_options
def enroll(name, podcast, sample, rebuild):
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
@with_global_options
def import_speaker_cmd(name, from_podcast, to_podcast):
    """Import a speaker from one podcast to another."""
    ctx = click.get_current_context()
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
@with_global_options
def list_speakers_cmd(podcast):
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
@with_global_options
def config(show, set_value, init_config):
    """Manage configuration."""
    ctx = click.get_current_context()
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
@with_global_options
def extract_samples_cmd(audio_file, podcast, output):
    """Extract speaker voice samples from an audio file."""
    ctx = click.get_current_context()
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
            output_path=audio_file.with_name(audio_file.stem + "-transcript.md"),
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


def _current_log_path() -> str | None:
    for h in logging.root.handlers:
        if h.get_name() == _FILE_HANDLER_NAME:
            path = getattr(h, "baseFilename", None)
            if path:
                return path
    return None


def _entrypoint() -> None:
    try:
        main(standalone_mode=False)
    except click.exceptions.Exit as e:
        sys.exit(e.exit_code)
    except click.exceptions.Abort:
        click.echo("Aborted.", err=True)
        sys.exit(1)
    except click.exceptions.UsageError as e:
        e.show()
        sys.exit(e.exit_code)
    except Exception as e:
        logger.exception("Unhandled exception")
        msg = _friendly_message(e)
        click.echo(f"Error: {msg}", err=True)
        log_path = _current_log_path()
        if log_path:
            click.echo(f"Details: {log_path}", err=True)
        else:
            click.echo("Use --log-level debug for details.", err=True)
        sys.exit(1)


if __name__ == "__main__":
    _entrypoint()
