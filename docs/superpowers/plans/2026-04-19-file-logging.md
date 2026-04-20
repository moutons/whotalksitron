# File Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add always-on debug file logging with gzip rotation so every CLI run is recorded for troubleshooting.

**Architecture:** A `RotatingFileHandler` at DEBUG level writes JSON lines to `~/.config/whotalksitron/whotalksitron.log`. The existing console handler is unchanged. `_setup_logging()` is refactored to only replace the console handler on the second call, preserving the file handler for the process lifetime. Rotation compresses backups with gzip via atomic temp-file rename.

**Tech Stack:** Python stdlib `logging.handlers.RotatingFileHandler`, `gzip`, `json`, `os.replace()`

**Spec:** `docs/superpowers/specs/2026-04-19-file-logging-design.md`

---

### Task 1: Add logging config fields to Config [sonnet]

**Files:**
- Modify: `src/whotalksitron/config.py:14-39` (Config dataclass)
- Modify: `src/whotalksitron/config.py:53-109` (from_dict)
- Modify: `src/whotalksitron/config.py:121-145` (show)
- Modify: `src/whotalksitron/config.py:147-183` (write_default)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing tests for new config fields**

Add to `tests/test_config.py`:

```python
_DEFAULT_LOG_FILE = str(Path.home() / ".config" / "whotalksitron" / "whotalksitron.log")


def test_default_config_logging_fields():
    cfg = Config()
    assert cfg.log_file == _DEFAULT_LOG_FILE
    assert cfg.log_file_max_bytes == 10_485_760
    assert cfg.log_file_backup_count == 5


def test_config_from_dict_logging():
    cfg = Config.from_dict(
        {
            "logging": {
                "file": "/tmp/test.log",
                "file_max_bytes": 5_000_000,
                "file_backup_count": 3,
            }
        }
    )
    assert cfg.log_file == "/tmp/test.log"
    assert cfg.log_file_max_bytes == 5_000_000
    assert cfg.log_file_backup_count == 3


def test_config_logging_tilde_expansion():
    cfg = Config.from_dict(
        {"logging": {"file": "~/custom.log"}}
    )
    assert cfg.log_file == str(Path.home() / "custom.log")


def test_config_logging_empty_disables():
    cfg = Config.from_dict({"logging": {"file": ""}})
    assert cfg.log_file == ""


def test_config_logging_whitespace_disables():
    cfg = Config.from_dict({"logging": {"file": "  "}})
    assert cfg.log_file == ""


def test_config_logging_max_bytes_floor():
    cfg = Config.from_dict({"logging": {"file_max_bytes": 100}})
    assert cfg.log_file_max_bytes == 10_485_760  # falls back to default


def test_config_logging_max_bytes_ceiling():
    cfg = Config.from_dict({"logging": {"file_max_bytes": 2_000_000_000}})
    assert cfg.log_file_max_bytes == 10_485_760  # falls back to default


def test_config_logging_backup_count_floor():
    cfg = Config.from_dict({"logging": {"file_backup_count": 0}})
    assert cfg.log_file_backup_count == 5  # falls back to default


def test_config_logging_backup_count_ceiling():
    cfg = Config.from_dict({"logging": {"file_backup_count": 50}})
    assert cfg.log_file_backup_count == 5  # falls back to default
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `just test -- tests/test_config.py -v -k "logging"`
Expected: FAIL — `Config` has no `log_file` attribute

- [ ] **Step 3: Add fields to Config dataclass**

In `src/whotalksitron/config.py`, add after `timestamp_format`:

```python
    log_file: str = ""  # set in __post_init__
    log_file_max_bytes: int = 10_485_760
    log_file_backup_count: int = 5

    def __post_init__(self):
        if not self.log_file:
            self.log_file = str(Path.home() / ".config" / "whotalksitron" / "whotalksitron.log")
```

- [ ] **Step 4: Add `[logging]` parsing to `from_dict`**

In `Config.from_dict()`, after the `output` block:

```python
        log = data.get("logging", {})
        if "file" in log:
            raw = str(log["file"]).strip()
            if raw:
                cfg.log_file = str(Path(raw).expanduser())
            else:
                cfg.log_file = ""
        if "file_max_bytes" in log:
            val = log["file_max_bytes"]
            if not (1_048_576 <= val <= 1_073_741_824):
                logger.warning(
                    "log_file_max_bytes=%d out of range [1MB, 1GB], using default", val
                )
            else:
                cfg.log_file_max_bytes = val
        if "file_backup_count" in log:
            val = log["file_backup_count"]
            if not (1 <= val <= 10):
                logger.warning(
                    "log_file_backup_count=%d out of range [1, 10], using default", val
                )
            else:
                cfg.log_file_backup_count = val
```

- [ ] **Step 5: Add logging fields to `show()` and `write_default()`**

In `show()`, after the `speakers.match_threshold` line:

```python
        lines.append(f"logging.file = {self.log_file!r}")
        lines.append(f"logging.file_max_bytes = {self.log_file_max_bytes!r}")
        lines.append(f"logging.file_backup_count = {self.log_file_backup_count!r}")
```

In `write_default()`, add to the `data` dict:

```python
            "logging": {
                "file": str(Path.home() / ".config" / "whotalksitron" / "whotalksitron.log"),
                "file_max_bytes": self.log_file_max_bytes,
                "file_backup_count": self.log_file_backup_count,
            },
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `just test -- tests/test_config.py -v -k "logging"`
Expected: All 8 new tests PASS

- [ ] **Step 7: Run full test suite**

Run: `just test`
Expected: All tests PASS (no regressions)

`[COMMIT]` `feat(config): add logging file, max_bytes, backup_count fields`

---

### Task 2: Refactor _setup_logging to preserve file handler [sonnet]

**Files:**
- Modify: `src/whotalksitron/cli.py:17-38` (_setup_logging)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing test for handler preservation**

Add to `tests/test_cli.py`:

```python
import logging


def test_setup_logging_preserves_non_console_handlers():
    """_setup_logging must only replace the console handler, not clear all handlers."""
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
            isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
            for h in logging.root.handlers
        ), "Console handler not present"
    finally:
        logging.root.removeHandler(dummy)
        dummy.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `just test -- tests/test_cli.py::test_setup_logging_preserves_non_console_handlers -v`
Expected: FAIL — current code calls `handlers.clear()`

- [ ] **Step 3: Refactor _setup_logging**

Replace the `_setup_logging` function in `src/whotalksitron/cli.py`:

```python
_CONSOLE_HANDLER_NAME = "whotalksitron_console"


def _setup_logging(level: str, fmt: str) -> None:
    numeric = getattr(logging, level.upper(), logging.INFO)

    # Remove only the console handler, preserve file and other handlers
    for h in logging.root.handlers[:]:
        if h.get_name() == _CONSOLE_HANDLER_NAME:
            logging.root.removeHandler(h)

    handler = logging.StreamHandler(sys.stderr)
    handler.set_name(_CONSOLE_HANDLER_NAME)
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
    logging.root.addHandler(handler)
    logging.root.setLevel(numeric)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `just test -- tests/test_cli.py::test_setup_logging_preserves_non_console_handlers -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `just test`
Expected: All tests PASS

`[COMMIT]` `refactor(cli): preserve non-console handlers across _setup_logging calls`

---

### Task 3: Add file handler with JSON formatter and gzip rotation [sonnet]

**Files:**
- Modify: `src/whotalksitron/cli.py` (add `_setup_file_logging` function)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests for file logging**

Add to `tests/test_cli.py`:

```python
import gzip
import json


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

    handler = _setup_file_logging("/no/such/dir/test.log", max_bytes=1_048_576, backup_count=3)
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `just test -- tests/test_cli.py -v -k "file_handler"`
Expected: FAIL — `_setup_file_logging` does not exist

- [ ] **Step 3: Implement _setup_file_logging**

Add to `src/whotalksitron/cli.py`, after the `_setup_logging` function:

```python
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
    from datetime import datetime, timezone
    from logging.handlers import RotatingFileHandler

    log_path = Path(log_file)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"Warning: cannot create log directory {log_path.parent}: {e}", file=sys.stderr)
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
        tmp_fd, tmp_path = tempfile.mkstemp(
            suffix=".gz", dir=str(log_path.parent)
        )
        try:
            with os.fdopen(tmp_fd, "wb") as tmp_f:
                with gzip.GzipFile(fileobj=tmp_f, mode="wb") as gz:
                    with open(source, "rb") as src:
                        while chunk := src.read(65536):
                            gz.write(chunk)
            os.replace(tmp_path, dest)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        os.unlink(source)

    handler.namer = _namer
    handler.rotator = _rotator

    class FileJsonFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            data = {
                "ts": datetime.fromtimestamp(
                    record.created, tz=timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
                + "Z",
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
            if hasattr(record, "argv"):
                data["argv"] = record.argv
            if hasattr(record, "version"):
                data["version"] = record.version
            return json.dumps(data)

    handler.setFormatter(FileJsonFormatter())
    handler.setLevel(logging.DEBUG)
    return handler
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `just test -- tests/test_cli.py -v -k "file_handler"`
Expected: All 5 new tests PASS

- [ ] **Step 5: Run full test suite**

Run: `just test`
Expected: All tests PASS

`[COMMIT]` `feat(cli): add _setup_file_logging with JSON format and gzip rotation`

`[REVIEW:light]` — 3 tasks committed, review recent delta

---

### Task 4: Wire file handler into _init_context and log invocation [sonnet]

**Files:**
- Modify: `src/whotalksitron/cli.py:61-91` (_init_context)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests for invocation logging and wiring**

Add to `tests/test_cli.py`:

```python
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
    # Simulate a flag with "key" in the name
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
    assert sanitized == ["--api-key", "***", "--token", "***", "--password", "***", "file.mp3"]


def test_sanitize_argv_equals_form():
    from whotalksitron.cli import _sanitize_argv

    argv = ["--api-key=secret123", "--backend", "gemini"]
    sanitized = _sanitize_argv(argv)
    assert sanitized[0] == "--api-key=***"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `just test -- tests/test_cli.py -v -k "invocation or sanitize"`
Expected: FAIL — `_sanitize_argv` does not exist

- [ ] **Step 3: Implement _sanitize_argv**

Add to `src/whotalksitron/cli.py`, after imports:

```python
import re

_SECRET_FLAG_PATTERN = re.compile(r"-{1,2}[a-z_-]*(key|token|secret|password)[a-z_-]*", re.IGNORECASE)


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
```

- [ ] **Step 4: Wire file handler into _init_context**

Modify `_init_context` in `src/whotalksitron/cli.py`. After `ctx.obj["config"] = cfg` (line 89), add file handler setup and invocation logging:

```python
    # Set up file logging (once per process)
    if not any(
        h.get_name() == _FILE_HANDLER_NAME for h in logging.root.handlers
    ):
        file_handler = _setup_file_logging(
            cfg.log_file, cfg.log_file_max_bytes, cfg.log_file_backup_count
        )
        if file_handler:
            logging.root.addHandler(file_handler)
            # Ensure root logger captures DEBUG for the file handler
            if logging.root.level > logging.DEBUG:
                logging.root.setLevel(logging.DEBUG)
                # But keep the console handler at its configured level
                for h in logging.root.handlers:
                    if h.get_name() == _CONSOLE_HANDLER_NAME:
                        h.setLevel(_numeric_level(effective_level))

        # Log invocation record
        import sys as _sys

        argv = _sys.argv[1:] if len(_sys.argv) > 1 else []
        record = logger.makeRecord(
            logger.name,
            logging.INFO,
            "",
            0,
            "invocation",
            (),
            None,
        )
        record.argv = _sanitize_argv(argv)
        record.version = __version__
        logger.handle(record)
```

Also add a helper at module level:

```python
def _numeric_level(level: str) -> int:
    return getattr(logging, level.upper(), logging.INFO)
```

And update `_setup_logging` to use `_numeric_level` and set level on the console handler:

```python
def _setup_logging(level: str, fmt: str) -> None:
    numeric = _numeric_level(level)

    for h in logging.root.handlers[:]:
        if h.get_name() == _CONSOLE_HANDLER_NAME:
            logging.root.removeHandler(h)

    handler = logging.StreamHandler(sys.stderr)
    handler.set_name(_CONSOLE_HANDLER_NAME)
    handler.setLevel(numeric)
    # ... rest unchanged ...
    logging.root.addHandler(handler)
    logging.root.setLevel(logging.DEBUG)  # let root pass everything; handlers filter
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `just test -- tests/test_cli.py -v -k "invocation or sanitize"`
Expected: All 5 new tests PASS

- [ ] **Step 6: Run full test suite**

Run: `just test`
Expected: All tests PASS

`[COMMIT]` `feat(cli): wire file handler into init, log sanitized invocation record`

---

### Task 5: Update README with logging config section [haiku]

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add `[logging]` section to config reference**

In `README.md`, after the `[output]` section in the config file reference block (after `timestamp_format = "HH:MM:SS"`), add:

```toml
[logging]
file = "~/.config/whotalksitron/whotalksitron.log"
file_max_bytes = 10_485_760   # 10MB, range: 1MB-1GB
file_backup_count = 5         # range: 1-10
```

- [ ] **Step 2: Verify formatting**

Run: `just lint`
Expected: PASS

`[COMMIT]` `docs: add [logging] section to README config reference`

---

### Task 6: Update config --init to include logging section [haiku]

**Files:**
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write test that config --init includes logging section**

Add to `tests/test_cli.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it passes**

Run: `just test -- tests/test_cli.py::test_config_init_includes_logging -v`
Expected: PASS (write_default was updated in Task 1)

If it fails, the `write_default` changes in Task 1 need to be checked.

`[COMMIT]` `test: verify config --init includes logging section`

`[REVIEW:normal]` — self-contained feature complete, review full delta

---

### Task 7: End-to-end verification [sonnet]

**Files:** None (verification only)

- [ ] **Step 1: Run full CI**

Run: `just ensureci-sandbox`
Expected: All checks PASS

- [ ] **Step 2: Reinstall and test manually**

Run: `uv tool install . --force --reinstall`

Then run:
```bash
whotalksitron config --show 2>&1 | grep "logging"
```
Expected: Shows `logging.file`, `logging.file_max_bytes`, `logging.file_backup_count`

- [ ] **Step 3: Verify log file created**

Run:
```bash
whotalksitron config --show > /dev/null 2>&1
cat ~/.config/whotalksitron/whotalksitron.log | head -1 | python3 -m json.tool
```
Expected: JSON with `ts`, `level`, `logger`, `message` fields. First record has `"message": "invocation"`.

- [ ] **Step 4: Verify log file survives double _setup_logging**

Run:
```bash
whotalksitron --log-level debug config --show > /dev/null 2>&1
wc -l ~/.config/whotalksitron/whotalksitron.log
```
Expected: Multiple lines (not just 1), confirming the file handler persisted across both `_setup_logging` calls.
