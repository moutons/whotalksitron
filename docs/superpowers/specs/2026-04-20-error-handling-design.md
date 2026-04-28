# CLI Error Handling

## Goal

Replace raw tracebacks, third-party log noise, and shutdown logging crashes
with friendly error messages on the console. Full diagnostics go to the file
log only.

## Problems

Three issues degrade the CLI experience today:

1. **Raw tracebacks.** Unhandled exceptions (TimeoutError, RetryExhausted,
   google-genai ClientError) print full Python stack traces. Users see
   implementation details instead of actionable guidance.

2. **Third-party log noise.** INFO-level messages from httpx, google_genai,
   google.auth, and httpcore appear on stderr at the default log level. These
   are meaningless to the user.

3. **Shutdown logging crashes.** When the google-genai client's `__del__`
   fires during interpreter teardown, httpcore emits log records. The file
   handler's `FileJsonFormatter` tries to import `datetime`, but
   `sys.meta_path` is already `None`. Python prints a `--- Logging error ---`
   block to stderr.

## Design

All changes live in `cli.py`. No backend or pipeline code changes.

### Console Logger Filter

Add a filter to the console handler that passes only `whotalksitron.*`
loggers. This blocks httpx, google_genai, google.auth, and httpcore from the
console at every log level, including `--log-level debug`.

Third-party log records still reach the file handler, which has no filter.

Change the invocation record (`"invocation"`) from INFO to DEBUG so it appears
only with `--log-level debug`.

### Top-Level Exception Handler

Wrap the `main()` entry point in a single `try/except Exception` that:

1. Logs the full traceback to the file log via `logger.exception()`.
2. Extracts a friendly one-liner from the exception.
3. Prints it with `click.echo(f"Error: {message}", err=True)`.
4. Appends `"Details: {log_file_path}"` when file logging is active, or
   `"Use --log-level debug for details."` when it is not.
5. Exits with code 1.

Existing per-command catches for `ValidationError`, `PreprocessingError`, and
`BackendUnavailableError` remain unchanged. They already produce good output
and exit before the top-level handler runs.

#### Friendly Message Table

The handler walks the exception's `__cause__` chain to find the most specific
match. `RetryExhausted` always delegates to its inner cause.

**Gemini / Google Cloud errors:**

| Exception | Condition | Message |
|-----------|-----------|---------|
| `google.genai.errors.ClientError` | status 401 | `"Authentication failed. Check your API key or run: gcloud auth application-default login"` |
| `google.genai.errors.ClientError` | status 404 | `"Model not found: {model}. Check gemini.model in your config."` |
| `google.genai.errors.ClientError` | status 429 | `"Rate limited by Gemini API. Wait a moment and try again."` |
| `google.genai.errors.ClientError` | other 4xx | `"Gemini API error ({status_code}): {message}"` |
| `google.genai.errors.ServerError` | any 5xx | `"Gemini API server error ({status_code}). Try again later."` |
| `google.auth.exceptions.DefaultCredentialsError` | -- | `"No Google Cloud credentials found. Run: gcloud auth application-default login"` |
| `google.auth.exceptions.RefreshError` | -- | `"Google Cloud credentials expired. Run: gcloud auth application-default login"` |
| GCS `google.api_core.exceptions` | upload failure | `"Failed to upload to GCS bucket '{bucket}': {error}"` |

**Whisper backend errors:**

| Exception | Condition | Message |
|-----------|-----------|---------|
| `httpx.ConnectError` | whisper endpoint URL | `"Cannot connect to whisper endpoint at {endpoint}. Is the server running?"` |
| `httpx.TimeoutException` | whisper endpoint URL | `"Whisper endpoint timed out at {endpoint}. The server may be overloaded."` |
| `httpx.HTTPStatusError` | whisper endpoint URL | `"Whisper endpoint returned {status_code}. Check server logs at {endpoint}."` |

**Pyannote backend errors:**

| Exception | Condition | Message |
|-----------|-----------|---------|
| `ImportError` | torch/pyannote missing | `"Pyannote backend requires extra dependencies. Install: uv tool install whotalksitron --with local"` |
| `RuntimeError` | message contains "CUDA", "torch", or "pyannote" | `"Pyannote error: {message}. Try --backend gemini or check device settings."` |

**General errors:**

| Exception | Message |
|-----------|---------|
| `TimeoutError` | `"Operation timed out. Check your network connection and try again."` |
| `httpx.ConnectError` | `"Cannot connect to {host}. Check your network connection."` |
| `httpx.TimeoutException` | `"Request timed out. Check your network connection and try again."` |
| `OSError` | `"Cannot read/write file: {path}: {error}"` |
| `RuntimeError` | `str(exc)` (already friendly from backend code) |
| Everything else | `"Unexpected error: {one-line summary}"` |

The handler checks exceptions in specificity order: library-specific first,
then general types.

To distinguish whisper httpx errors from other httpx errors, the handler
inspects the exception's `request.url` attribute when present.

### Shutdown Cleanup

Register an `atexit` handler when the file handler is created. The handler
flushes the file handler, removes it from the root logger, and closes it. This
runs before interpreter teardown begins, preventing the google-genai client's
`__del__` from triggering log records against a dead formatter.

```python
atexit.register(_cleanup_file_handler)
```

## Testing

- Test the console filter passes `whotalksitron.*` and blocks `httpx.*`.
- Test `_friendly_message()` for each exception type in the table.
- Test the `__cause__` chain walking (RetryExhausted wrapping ClientError).
- Test the atexit handler removes the file handler from root logger.
- Test that unknown exceptions produce the generic message with log path.

## Files

- Modify: `src/whotalksitron/cli.py`
- Modify: `tests/test_cli.py`
