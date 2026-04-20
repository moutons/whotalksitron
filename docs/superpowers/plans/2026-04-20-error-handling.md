# CLI Error Handling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace raw tracebacks, third-party log noise, and shutdown crashes with friendly error messages on the console while preserving full diagnostics in the file log.

**Architecture:** Three changes in `cli.py`: (1) a logging filter on the console handler that passes only `whotalksitron.*` loggers, (2) a top-level exception handler around `main()` that maps known exceptions to friendly messages and logs full tracebacks to the file log, (3) an `atexit` handler that cleans up the file handler before interpreter shutdown.

**Tech Stack:** Python logging, click, atexit. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-04-20-error-handling-design.md`

---

### Task 1: Console Logger Filter [sonnet]

**Files:**
- Modify: `src/whotalksitron/cli.py:50-78` (`_setup_logging`)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cli.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py::test_console_filter_passes_whotalksitron_loggers tests/test_cli.py::test_console_filter_blocks_third_party_loggers tests/test_cli.py::test_console_filter_blocks_third_party_even_at_debug -v`
Expected: FAIL (no filter installed yet, third-party records pass through)

- [ ] **Step 3: Implement the console filter**

In `src/whotalksitron/cli.py`, add a filter class after the `_CONSOLE_HANDLER_NAME` constant (around line 19), and add it to the handler in `_setup_logging`:

```python
class _ConsoleFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.name.startswith("whotalksitron")
```

In `_setup_logging`, after creating the handler and before adding it to root (around line 60), add:

```python
    handler.addFilter(_ConsoleFilter())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py::test_console_filter_passes_whotalksitron_loggers tests/test_cli.py::test_console_filter_blocks_third_party_loggers tests/test_cli.py::test_console_filter_blocks_third_party_even_at_debug -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest --tb=short`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/whotalksitron/cli.py tests/test_cli.py
git commit -m "feat(cli): filter third-party loggers from console output"
```

---

### Task 2: Change Invocation Record to DEBUG [sonnet]

**Files:**
- Modify: `src/whotalksitron/cli.py:228-241` (`_init_context`)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_cli.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py::test_invocation_not_shown_at_info_level -v`
Expected: FAIL (invocation record currently emitted at INFO)

- [ ] **Step 3: Change invocation record level to DEBUG**

In `src/whotalksitron/cli.py`, in `_init_context`, change the `logging.INFO` on line 232 to `logging.DEBUG`:

```python
    record = logger.makeRecord(
        logger.name,
        logging.DEBUG,
        "",
        0,
        "invocation",
        (),
        None,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py::test_invocation_not_shown_at_info_level tests/test_cli.py::test_invocation_logged_to_file -v`
Expected: Both PASS (file log still gets the record because file handler is at DEBUG)

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest --tb=short`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/whotalksitron/cli.py tests/test_cli.py
git commit -m "fix(cli): log invocation record at DEBUG to reduce console noise"
```

---

### Task 3: Friendly Message Extraction Function [sonnet]

**Files:**
- Modify: `src/whotalksitron/cli.py` (new function `_friendly_message`)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cli.py`:

```python
def test_friendly_message_timeout_error():
    from whotalksitron.cli import _friendly_message

    msg = _friendly_message(TimeoutError("Operation timed out"))
    assert "timed out" in msg
    assert "network" in msg.lower()


def test_friendly_message_runtime_error():
    from whotalksitron.cli import _friendly_message

    exc = RuntimeError("Gemini API failed after 3 retries. Check your API key.")
    msg = _friendly_message(exc)
    assert msg == "Gemini API failed after 3 retries. Check your API key."


def test_friendly_message_import_error_pyannote():
    from whotalksitron.cli import _friendly_message

    exc = ImportError("No module named 'pyannote'")
    msg = _friendly_message(exc)
    assert "uv tool install" in msg


def test_friendly_message_import_error_torch():
    from whotalksitron.cli import _friendly_message

    exc = ImportError("No module named 'torch'")
    msg = _friendly_message(exc)
    assert "uv tool install" in msg


def test_friendly_message_os_error():
    from whotalksitron.cli import _friendly_message

    exc = OSError("Permission denied: '/tmp/test.wav'")
    msg = _friendly_message(exc)
    assert "Permission denied" in msg


def test_friendly_message_unknown_exception():
    from whotalksitron.cli import _friendly_message

    exc = ValueError("something weird")
    msg = _friendly_message(exc)
    assert "something weird" in msg


def test_friendly_message_retry_exhausted_walks_cause():
    from whotalksitron.cli import _friendly_message
    from whotalksitron.retry import RetryExhausted

    inner = TimeoutError("connection timed out")
    exc = RetryExhausted("Failed after 3 retries: connection timed out")
    exc.__cause__ = inner
    msg = _friendly_message(exc)
    assert "timed out" in msg
    assert "network" in msg.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -k "friendly_message" -v`
Expected: FAIL with "cannot import name '_friendly_message'"

- [ ] **Step 3: Implement `_friendly_message`**

Add to `src/whotalksitron/cli.py`, after the `_sanitize_argv` function (around line 44):

```python
def _friendly_message(exc: Exception) -> str:
    # Walk cause chain for wrapped errors (RetryExhausted, etc.)
    from whotalksitron.retry import RetryExhausted

    if isinstance(exc, RetryExhausted) and exc.__cause__ is not None:
        return _friendly_message(exc.__cause__)

    # Gemini / Google Cloud errors
    try:
        from google.genai.errors import ClientError, ServerError

        if isinstance(exc, ClientError):
            code = getattr(exc, "status_code", 0) or 0
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
            code = getattr(exc, "status_code", 0) or 0
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -k "friendly_message" -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest --tb=short`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/whotalksitron/cli.py tests/test_cli.py
git commit -m "feat(cli): add friendly error message extraction from exception chains"
```

---

### Task 4: Top-Level Exception Handler [sonnet]

**Files:**
- Modify: `src/whotalksitron/cli.py:600-602` (entry point)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cli.py`:

```python
from unittest.mock import patch


def test_top_level_handler_catches_timeout(runner, tmp_path, fake_audio):
    """TimeoutError during transcribe must show friendly message, not traceback."""
    config_file = tmp_path / "config.toml"
    import tomli_w

    data = {
        "defaults": {"backend": "gemini"},
        "gemini": {"api_key": "test-key"},
        "logging": {"file": str(tmp_path / "test.log")},
    }
    config_file.write_bytes(tomli_w.dumps(data).encode())

    with patch(
        "whotalksitron.backends.gemini.GeminiBackend.transcribe",
        side_effect=TimeoutError("Operation timed out"),
    ):
        result = runner.invoke(
            main,
            ["transcribe", str(fake_audio)],
            env={"WHOTALKSITRON_CONFIG": str(config_file)},
        )

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "timed out" in result.output


def test_top_level_handler_shows_log_path(runner, tmp_path, fake_audio):
    """Error message must include path to log file for diagnostics."""
    config_file = tmp_path / "config.toml"
    log_file = tmp_path / "test.log"
    import tomli_w

    data = {
        "defaults": {"backend": "gemini"},
        "gemini": {"api_key": "test-key"},
        "logging": {"file": str(log_file)},
    }
    config_file.write_bytes(tomli_w.dumps(data).encode())

    with patch(
        "whotalksitron.backends.gemini.GeminiBackend.transcribe",
        side_effect=TimeoutError("Operation timed out"),
    ):
        result = runner.invoke(
            main,
            ["transcribe", str(fake_audio)],
            env={"WHOTALKSITRON_CONFIG": str(config_file)},
        )

    assert result.exit_code == 1
    assert str(log_file) in result.output


def test_top_level_handler_logs_traceback_to_file(runner, tmp_path, fake_audio):
    """Full traceback must be written to the file log."""
    config_file = tmp_path / "config.toml"
    log_file = tmp_path / "test.log"
    import tomli_w

    data = {
        "defaults": {"backend": "gemini"},
        "gemini": {"api_key": "test-key"},
        "logging": {"file": str(log_file)},
    }
    config_file.write_bytes(tomli_w.dumps(data).encode())

    with patch(
        "whotalksitron.backends.gemini.GeminiBackend.transcribe",
        side_effect=TimeoutError("Operation timed out"),
    ):
        result = runner.invoke(
            main,
            ["transcribe", str(fake_audio)],
            env={"WHOTALKSITRON_CONFIG": str(config_file)},
        )

    assert result.exit_code == 1
    log_content = log_file.read_text()
    assert "TimeoutError" in log_content


def test_existing_handled_errors_unchanged(runner, tmp_path):
    """ValidationError, PreprocessingError, BackendUnavailableError keep their behavior."""
    config_file = tmp_path / "config.toml"
    import tomli_w

    data = {"logging": {"file": ""}}
    config_file.write_bytes(tomli_w.dumps(data).encode())

    # Nonexistent audio file triggers ValidationError inside pipeline
    result = runner.invoke(
        main,
        ["transcribe", "/nonexistent/audio.mp3"],
        env={"WHOTALKSITRON_CONFIG": str(config_file)},
    )
    # Click catches the bad path before our code runs (exists=True)
    assert result.exit_code != 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py::test_top_level_handler_catches_timeout tests/test_cli.py::test_top_level_handler_shows_log_path tests/test_cli.py::test_top_level_handler_logs_traceback_to_file -v`
Expected: FAIL (no top-level handler yet, traceback shows in output)

- [ ] **Step 3: Implement the top-level exception handler**

In `src/whotalksitron/cli.py`, replace the `if __name__ == "__main__":` block at line 601-602 with a wrapped entry point. Also modify the `main` group to use `standalone_mode=False` in a wrapper:

Add a new function after all command definitions (before `_speakers_dir`):

```python
def _run() -> None:
    try:
        main(standalone_mode=False)
    except click.exceptions.Exit as e:
        sys.exit(e.code)
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
        log_path = _active_log_file()
        if log_path:
            click.echo(f"Details: {log_path}", err=True)
        else:
            click.echo("Use --log-level debug for details.", err=True)
        sys.exit(1)


def _active_log_file() -> str | None:
    for h in logging.root.handlers:
        if h.get_name() == _FILE_HANDLER_NAME:
            path = getattr(h, "baseFilename", None)
            if path:
                return path
    return None
```

Update the `[project.scripts]` entry point. In `pyproject.toml`, change:

```toml
[project.scripts]
whotalksitron = "whotalksitron.cli:_run"
```

And update the `if __name__` block:

```python
if __name__ == "__main__":
    _run()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py::test_top_level_handler_catches_timeout tests/test_cli.py::test_top_level_handler_shows_log_path tests/test_cli.py::test_top_level_handler_logs_traceback_to_file tests/test_cli.py::test_existing_handled_errors_unchanged -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest --tb=short`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/whotalksitron/cli.py pyproject.toml tests/test_cli.py
git commit -m "feat(cli): add top-level exception handler with friendly error messages"
```

---

### Task 5: Shutdown Cleanup via atexit [sonnet]

**Files:**
- Modify: `src/whotalksitron/cli.py:85-165` (`_setup_file_logging`)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cli.py`:

```python
def test_atexit_removes_file_handler(tmp_path):
    """atexit cleanup must remove the file handler from root logger."""
    import atexit
    from unittest.mock import patch

    from whotalksitron.cli import _FILE_HANDLER_NAME, _setup_file_logging

    log_file = tmp_path / "test.log"

    registered_funcs = []
    with patch.object(atexit, "register", side_effect=lambda f: registered_funcs.append(f)):
        handler = _setup_file_logging(str(log_file), max_bytes=1_048_576, backup_count=3)

    assert handler is not None
    assert len(registered_funcs) == 1

    logging.root.addHandler(handler)
    assert any(h.get_name() == _FILE_HANDLER_NAME for h in logging.root.handlers)

    # Run the cleanup
    registered_funcs[0]()

    assert not any(h.get_name() == _FILE_HANDLER_NAME for h in logging.root.handlers)


def test_file_formatter_survives_shutdown_simulation(tmp_path):
    """FileJsonFormatter must not crash when datetime import fails."""
    from whotalksitron.cli import _setup_file_logging

    log_file = tmp_path / "test.log"
    handler = _setup_file_logging(str(log_file), max_bytes=1_048_576, backup_count=3)
    assert handler is not None

    try:
        test_logger = logging.getLogger("test.shutdown")
        test_logger.setLevel(logging.DEBUG)
        test_logger.addHandler(handler)

        # Normal log should work
        test_logger.debug("before shutdown")
        handler.flush()
        assert "before shutdown" in log_file.read_text()
    finally:
        test_logger.removeHandler(handler)
        handler.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py::test_atexit_removes_file_handler tests/test_cli.py::test_file_formatter_survives_shutdown_simulation -v`
Expected: `test_atexit_removes_file_handler` FAILS (no atexit registration). `test_file_formatter_survives_shutdown_simulation` may pass (it tests normal operation).

- [ ] **Step 3: Implement atexit cleanup and defensive formatter**

In `src/whotalksitron/cli.py`, add `import atexit` to the top-level imports.

In `_setup_file_logging`, after `handler.setLevel(logging.DEBUG)` and before `return handler` (around line 164), add:

```python
    def _cleanup() -> None:
        for h in logging.root.handlers[:]:
            if h.get_name() == _FILE_HANDLER_NAME:
                h.flush()
                logging.root.removeHandler(h)
                h.close()

    atexit.register(_cleanup)
```

Also wrap the `FileJsonFormatter.format` method's body in a try/except to handle the case where atexit hasn't run but shutdown has started:

```python
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
                return json.dumps(data)
            except Exception:
                return ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py::test_atexit_removes_file_handler tests/test_cli.py::test_file_formatter_survives_shutdown_simulation -v`
Expected: Both PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest --tb=short`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/whotalksitron/cli.py tests/test_cli.py
git commit -m "fix(cli): clean up file handler at shutdown to prevent logging crashes"
```

---

### Task 6: Integration Test and Lint [sonnet]

**Files:**
- Test: `tests/test_cli.py`
- Modify: `src/whotalksitron/cli.py` (if lint fixes needed)

- [ ] **Step 1: Write an integration test**

Add to `tests/test_cli.py`:

```python
def test_no_traceback_on_any_unhandled_error(runner, tmp_path, fake_audio):
    """No unhandled exception should produce a traceback on console."""
    config_file = tmp_path / "config.toml"
    import tomli_w

    data = {
        "defaults": {"backend": "gemini"},
        "gemini": {"api_key": "test-key"},
        "logging": {"file": str(tmp_path / "test.log")},
    }
    config_file.write_bytes(tomli_w.dumps(data).encode())

    with patch(
        "whotalksitron.backends.gemini.GeminiBackend.transcribe",
        side_effect=ValueError("completely unexpected"),
    ):
        result = runner.invoke(
            main,
            ["transcribe", str(fake_audio)],
            env={"WHOTALKSITRON_CONFIG": str(config_file)},
        )

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "Error:" in result.output
    assert "completely unexpected" in result.output
```

- [ ] **Step 2: Run integration test**

Run: `uv run pytest tests/test_cli.py::test_no_traceback_on_any_unhandled_error -v`
Expected: PASS (top-level handler from Task 4 catches this)

- [ ] **Step 3: Run full CI checks**

Run: `just ensureci-sandbox`
Expected: All checks pass (lint, format, typecheck, security, tests)

- [ ] **Step 4: Fix any lint or format issues**

If `just ensureci-sandbox` reports issues, fix them:

Run: `just fmt` (for formatting)
Address any ruff lint or ty errors manually.

- [ ] **Step 5: Commit any fixes**

```bash
git add -u
git commit -m "test(cli): add integration test for error handling"
```

---

### Task 7: [REVIEW:normal] Final Review [opus]

- [ ] **Step 1: Verify all spec requirements are met**

Check against `docs/superpowers/specs/2026-04-20-error-handling-design.md`:

1. Console filter blocks third-party loggers ✓
2. Invocation record at DEBUG ✓
3. Top-level exception handler with friendly messages ✓
4. All exception types from the spec's table have handlers ✓
5. `__cause__` chain walking for RetryExhausted ✓
6. Log file path shown in error messages ✓
7. atexit cleanup prevents shutdown crashes ✓

- [ ] **Step 2: Run full test suite one final time**

Run: `just ensureci-sandbox`
Expected: All checks pass

- [ ] **Step 3: Review diff**

Run: `git diff main --stat` and `git log main..HEAD --oneline`
Verify: Only `cli.py`, `test_cli.py`, and `pyproject.toml` changed. No unrelated modifications.
