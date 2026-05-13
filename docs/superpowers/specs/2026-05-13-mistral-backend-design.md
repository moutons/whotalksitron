# Mistral Transcription Backend

**Date:** 2026-05-13
**Status:** Approved
**Scope:** Add a fourth `Backend` implementation that calls Mistral's
`/v1/audio/transcriptions` endpoint.

## Goal

Allow `whotalksitron` users to transcribe audio via Mistral's cloud
transcription API (Voxtral family) using `--backend mistral`. Provide the same
runtime secret-resolution ergonomics already used for the Gemini backend:
env var, macOS Keychain, or `op` CLI lookup.

## Non-goals

- Speaker diarization. Mistral's endpoint does not return speaker labels and
  this design does not add post-hoc diarization for the Mistral path.
- Auto-selection. The backend is opt-in via explicit configuration only.
- Chunking large files. We rely on Mistral's documented size limit and emit a
  friendly error if exceeded.
- Adoption of the `onepassword-sdk` Python package. We stay on the existing
  `op` CLI integration to keep the secret-store surface uniform.

## Architecture

New file `src/whotalksitron/backends/mistral.py` exporting a `MistralBackend`
class that satisfies the existing `Backend` protocol in
`src/whotalksitron/backends/__init__.py`. Structurally the closest analogue is
`whisper.py` (cloud-style HTTP POST, no diarization), with bearer-auth and
secret resolution borrowed from `gemini.py`.

### Component diagram

```
CLI / pipeline
   ↓
select_backend(config)         -- backends/__init__.py
   ↓ (when config.backend == "mistral")
MistralBackend.transcribe()    -- backends/mistral.py
   ↓
httpx.post(...)  →  api.mistral.ai/v1/audio/transcriptions
   ↓
parse JSON → TranscriptResult (speaker=None on every segment)
```

## Config changes

Add the following fields to `Config` in `src/whotalksitron/config.py`:

| Field | Default | Source |
|------|---------|--------|
| `mistral_api_key` | `""` | TOML, env `MISTRAL_API_KEY`, Keychain, 1Password |
| `mistral_endpoint` | `"https://api.mistral.ai/v1"` | TOML |
| `mistral_model` | `"voxtral-mini-latest"` | TOML |
| `mistral_keychain_account` | `"mistral"` | TOML |
| `mistral_keychain_service` | `"mistral-apikey"` | TOML |
| `mistral_op_reference` | `""` | TOML |

Wiring:

- `Config.from_dict` reads a `[mistral]` table with keys
  `api_key`, `endpoint`, `model`, `keychain_account`, `keychain_service`,
  `op_reference`.
- `Config.write_default` emits an empty `[mistral]` table mirroring the Gemini
  table layout.
- `Config.show` prints the masked key plus endpoint and model.
- `load_config` adds `MISTRAL_API_KEY` to `str_env_map`.

### Secret resolution refactor

The existing `_resolve_secret(cfg)` is hard-coded to Gemini fields. Refactor
to take explicit arguments:

```python
def _resolve_secret(
    keychain_account: str,
    keychain_service: str,
    op_reference: str,
) -> str | None: ...
```

`load_config` calls it twice:

1. If `cfg.gemini_api_key` is empty, resolve with the Gemini triple.
2. If `cfg.mistral_api_key` is empty, resolve with the Mistral triple.

No behavioural change for the Gemini path — same Keychain → `op read` order,
same timeouts, same log messages (parameterised on service name).

## Backend wiring

In `backends/__init__.py`:

- Add a `mistral` branch to `_create_backend` importing `MistralBackend`.
- Add a hint to `_unavailable_message`:
  `"Set MISTRAL_API_KEY, store the key in macOS Keychain
  (mistral/mistral-apikey), or set mistral.op_reference in config."`
- Do **not** add `mistral` to the `("gemini", "pyannote", "whisper")` tuple
  used by auto-select.

## API call

```
POST {mistral_endpoint}/audio/transcriptions
Authorization: Bearer <key>
Content-Type: multipart/form-data

  file: <audio bytes, filename = audio_path.name>
  model: <mistral_model>
  timestamp_granularities[]: segment
  response_format: verbose_json
```

Timeout: 600s (matches whisper backend). Retry: `retry_with_backoff(retries=3,
base_delay=2.0, retry_on=(httpx.HTTPStatusError, httpx.ConnectError,
httpx.ReadTimeout))`. On `RetryExhausted`, raise
`RuntimeError("Mistral API failed after 3 retries. Check MISTRAL_API_KEY and
network connectivity, or try a different backend.")`.

## Response parsing

Expected JSON shape:

```json
{
  "text": "...full transcript...",
  "segments": [
    {"start": 0.0, "end": 4.2, "text": "..."},
    ...
  ]
}
```

Parsing rules:

- If `segments` is a non-empty list, emit one `TranscriptSegment` per entry
  with `start`, `end`, `text=segment["text"].strip()`, `speaker=None`.
- If `segments` is missing or empty but `text` is non-empty, emit a single
  segment with `start=0.0`, `end=0.0`, `text=text.strip()`, `speaker=None`,
  and log an INFO warning that segment timestamps were unavailable.
- If both are missing/empty, log a WARNING and return a result with an
  empty segment list.

`TranscriptResult.metadata` includes `model`, `backend="mistral"`, and
`token_count=None` (Mistral does not return token usage on this endpoint).

## Diarization handling

`supports_diarization()` returns `False`.

When `transcribe()` is called with a non-empty `SpeakerPool`, log once at
INFO level:

> "Mistral backend ignores speaker enrollment; use gemini or pyannote for
> diarization."

Proceed normally. No error, no synthetic speaker labels.

## File size handling

No client-side size check. If the API returns HTTP 413, or any
`httpx.HTTPStatusError` whose response body indicates a size problem, raise

> `RuntimeError("Audio file exceeds Mistral's upload limit. Use the gemini
> backend (which supports large-file upload via the File API) or split the
> recording.")`

All other HTTP errors propagate through the retry/RuntimeError envelope.

## Progress reporting

Match the whisper backend's three-step pattern:

1. `progress.update("transcribe", 0, "sending to Mistral API")`
2. `progress.update("transcribe", 80, "parsing response")` after the POST
3. `progress.stage_complete("transcribe", f"{len(segments)} segments")`

## Testing

### `tests/test_backends/test_mistral.py`

- `is_available()` returns `True` when `mistral_api_key` is set, `False`
  otherwise.
- `transcribe()` happy path: mocks `httpx.post` to return a fixture JSON,
  asserts:
  - Request URL equals `f"{endpoint}/audio/transcriptions"`.
  - `Authorization: Bearer <key>` header is sent.
  - Multipart form contains `model`, `timestamp_granularities[]=segment`,
    `response_format=verbose_json`, and a file part.
  - Returned segments match the fixture and all have `speaker is None`.
- Empty `segments` array with non-empty `text` → single fallback segment +
  INFO log.
- `speakers` argument: passing a non-empty `SpeakerPool` logs the
  diarization-ignored notice and does not affect the request body.
- `supports_diarization()` returns `False`.
- HTTP 401 surfaces as `RuntimeError` after retries are exhausted.

### `tests/test_backends/test_selection.py`

- Explicit `backend = "mistral"` returns a `MistralBackend`.
- `mistral` is not picked by auto-select even when its key is the only one
  configured (auto falls through and raises `BackendUnavailableError`).

### `tests/test_config.py`

- `from_dict` reads the `[mistral]` table.
- `MISTRAL_API_KEY` env var overrides the file value.
- `_resolve_secret` is invoked separately for Mistral and Gemini with their
  respective Keychain/op coordinates (regression: Gemini behaviour unchanged).
- `Config.show()` masks the Mistral key.
- `write_default` round-trips through `from_file`.

## Documentation

- Update `docs/backends` to add a Mistral row with auth, diarization,
  size limit, and config snippet.
- Update `README.md` backend comparison table.
- Add an entry under `[Unreleased]` in `CHANGELOG.md`:
  `feat(backends): add Mistral transcription backend (voxtral-mini)`.

## Out of scope / future work

- Adding `mistral` to the auto-select chain (revisit once diarization is
  available via a Mistral endpoint, or once a post-hoc diarization pipeline
  exists).
- Chunked uploads for files exceeding Mistral's size cap.
- Adoption of the `onepassword-sdk` Python package as an alternative to the
  `op` CLI for any backend.
- Returning Mistral usage metadata once the API exposes it.
