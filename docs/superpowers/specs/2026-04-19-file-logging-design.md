# File Logging

Always-on debug logging to a local file for post-hoc troubleshooting.

## Scope

**In scope:** persistent file logger with rotation and compression, invocation recording, config keys.

**Out of scope:** remote log shipping, log aggregation, changes to console logging behavior.

## Architecture

Two independent handlers on the root logger:

1. **Console handler** (existing) -- `StreamHandler(stderr)`. Level and format controlled by `--log-level` / `--log-format`. Unchanged.
2. **File handler** (new) -- `RotatingFileHandler` at DEBUG level. Always JSON. Always active unless `log_file` is set to empty string.

**Handler lifecycle:** `_setup_logging()` is called twice per run -- once early with defaults, again after config loads. The current implementation calls `logging.root.handlers.clear()` which would destroy the file handler on the second call. The fix: `_setup_logging()` must only remove and replace the console handler, leaving the file handler untouched. The file handler is created once (after the first `_setup_logging()` call when defaults are available) and persists for the process lifetime.

## Log file location

Default: `~/.config/whotalksitron/whotalksitron.log`

Rotated backups: `whotalksitron.log.1.gz` through `whotalksitron.log.5.gz`.

Maximum disk footprint: ~50MB (10MB active + 5 compressed backups).

## JSON line format

Every log line is a single JSON object:

```json
{"ts": "2026-04-19T21:15:03.412Z", "level": "DEBUG", "logger": "whotalksitron.backends.gemini", "message": "Gemini response length: 183422 chars"}
```

Fields:

| Field | Type | Description |
|---|---|---|
| `ts` | string | ISO 8601 UTC timestamp with milliseconds |
| `level` | string | Log level (DEBUG, INFO, WARNING, ERROR) |
| `logger` | string | Logger name (module path) |
| `message` | string | Log message |

Additional fields may appear on specific records (see invocation record below). All serialization uses `json.dumps()`, never string interpolation.

## Invocation record

First log line of every run (emitted once after final `_setup_logging()` call) includes CLI arguments and version:

```json
{"ts": "...", "level": "INFO", "logger": "whotalksitron.cli", "message": "invocation", "argv": ["transcribe", "--backend", "gemini", "episode.mp3"], "version": "0.1.0"}
```

This allows reconstructing the exact command that produced subsequent log lines. The argv list is sanitized before logging: any flag whose name contains "key", "token", "secret", or "password" has its value replaced with `"***"`. Currently no such flags exist, but this guards against future additions.

## Rotation with gzip compression

Python's `RotatingFileHandler` with custom `namer` and `rotator`:

- `namer`: appends `.gz` to rotated filenames
- `rotator`: writes the source file to a temp file via `gzip.open()`, then `os.replace()` to the target (atomic rename), then deletes the uncompressed source. If the target backup slot already exists, it is overwritten by `os.replace()`.

Rotation triggers when the active log file exceeds `file_max_bytes`.

## Configuration

Three new fields on `Config`, under a `[logging]` section in config.toml:

```toml
[logging]
file = "~/.config/whotalksitron/whotalksitron.log"
file_max_bytes = 10_485_760
file_backup_count = 5
```

| Field | Default | Description |
|---|---|---|
| `file` | `~/.config/whotalksitron/whotalksitron.log` | Log file path. Tilde is expanded at runtime. Value is stripped of whitespace; empty after strip disables file logging. |
| `file_max_bytes` | 10485760 (10MB) | Maximum size before rotation. Minimum 1MB, maximum 1GB. Out-of-range values fall back to the default with a stderr warning. |
| `file_backup_count` | 5 | Number of compressed backups to keep. Range 1--10. |

No environment variables. No CLI flags. This is a local preference configured once.

## Files changed

- `src/whotalksitron/config.py` -- add three fields, parse `[logging]` TOML section
- `src/whotalksitron/cli.py` -- update `_setup_logging()` to add file handler, log invocation at startup
- `tests/test_cli.py` -- test file handler creation, rotation, gzip compression, invocation record
- `README.md` -- document `[logging]` config section

## Error handling

If the log directory does not exist, create it (same `config_dir` used elsewhere). If the log file cannot be opened (permissions, disk full), warn on stderr and continue without file logging. File logging failure must never prevent the CLI from running.
