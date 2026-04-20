# Error Handling & Diagnostics

## Principle

Every anticipated failure produces an actionable message: what went wrong and what to do about it.

## Error Categories

### Configuration Errors

Detected before processing begins.

| Condition | Message |
|---|---|
| No backend available | List what each backend needs, with install/config commands |
| API key rejected | `GEMINI_API_KEY is set but rejected by the API. Verify at...` |
| Endpoint unreachable | `Ollama endpoint at http://localhost:1234 is not responding. Is Ollama running?` |
| No speakers enrolled | Warning (not error). Proceed with generic labels. |

### Input Errors

| Condition | Message |
|---|---|
| File not found / unreadable | Standard file error with full path |
| Unsupported format, no ffmpeg | `ffmpeg is required to convert .ogg files. Install: brew install ffmpeg` |
| File too large for backend | Suggest chunking or a different backend |

### Runtime Errors

| Condition | Behavior |
|---|---|
| API rate limit | Retry with exponential backoff (base 2s, max 3 retries). Log each retry at `info`. Uses `retry_with_backoff()` from `whotalksitron.retry`. |
| API timeout | Retry up to 3 times with backoff, then fail with actionable message suggesting a local backend. |
| pyannote OOM | `Model requires more RAM than available. Try whisper_model = "medium" in config.` |
| Partial failure | Emit transcript without speaker labels, warn clearly. Exit code 3. |

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | General error |
| 2 | Configuration or usage error |
| 3 | Partial success (transcript produced with degraded quality) |

Exit code 3 is important for callers. The transcript is usable but something went wrong (diarization failed, voiceprint matching timed out). Callers can flag it for review.

## Logging

Uses Python's `logging` module with a structured formatter.

- `--log-level debug` exposes: backend API calls and responses, timing per pipeline stage, model selection rationale, voiceprint match scores with enrolled speaker names, ffmpeg commands.
- `--log-format json` outputs structured log lines for ingestion by external tools.
- Logs go to stderr. Never to stdout.
