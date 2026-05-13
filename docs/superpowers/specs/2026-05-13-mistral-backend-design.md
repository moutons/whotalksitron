# Mistral Transcription Backend

**Date:** 2026-05-13
**Status:** Approved (revised after adversarial review)
**Scope:** Add a fourth `Backend` implementation that calls Mistral's
`/v1/audio/transcriptions` endpoint.

## Goal

Allow `whotalksitron` users to transcribe audio via Mistral's cloud
transcription API (Voxtral family) using `--backend mistral`. Provide the same
runtime secret-resolution ergonomics already used for the Gemini backend:
env var, macOS Keychain, or `op` CLI lookup.

## Non-goals

- **Diarization in this iteration.** Mistral's endpoint *does* support a
  `diarize=true` flag, but wiring diarization end-to-end (segment-to-speaker
  mapping, SpeakerPool integration) is deferred. This backend ships with
  `supports_diarization()` returning `False`.
- Auto-selection. The backend is opt-in via explicit configuration only.
- Chunking large files. We surface a friendly error on size/duration
  rejection and let the user split or use a different backend.
- Adoption of the `onepassword-sdk` Python package. We stay on the existing
  `op` CLI integration to keep the secret-store surface uniform across
  backends. (See "Out of scope" — eventual SDK migration is tracked.)

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

Note: `mistral_keychain_account = "mistral"` does not mirror Gemini's
`"vertex"` value because that field is the *cloud-provider* name in the
Gemini case, not the brand. For Mistral, brand and provider are the same,
so `"mistral"` is correct — do not "fix" it to `"voxtral"` or similar.

Wiring:

- `Config.from_dict` reads a `[mistral]` table with keys
  `api_key`, `endpoint`, `model`, `keychain_account`, `keychain_service`,
  `op_reference`.
- `Config.write_default` emits an empty `[mistral]` table mirroring the
  Gemini table layout.
- `Config.show` prints the masked key plus endpoint and model.
- `load_config` adds `MISTRAL_API_KEY` to `str_env_map`.
- `load_config` normalises `mistral_endpoint` with `.rstrip("/")` so the
  URL construction is robust against trailing slashes.
- `load_config` validates that `mistral_endpoint` has scheme `https://`
  (raise `ValueError` if not). Emits a WARNING log when the endpoint
  differs from the default — this is a security signal that the bearer
  token will be sent to a non-default host.

### Secret resolution refactor

The existing `_resolve_secret(cfg)` is hard-coded to Gemini fields. Refactor
to take explicit arguments:

```python
def _resolve_secret(
    *,
    keychain_account: str,
    keychain_service: str,
    op_reference: str,
) -> str | None: ...
```

Keyword-only arguments to prevent positional-argument transposition between
the two call sites.

`load_config` calls it twice, **only when the corresponding `*_api_key` is
still empty after the env-var pass**. Env var > Keychain > 1Password:

1. After `str_env_map` is applied, if `cfg.gemini_api_key` is empty,
   resolve with the Gemini triple.
2. If `cfg.mistral_api_key` is empty, resolve with the Mistral triple.

Log messages parameterise on the service name so operators can distinguish
Gemini vs Mistral resolution paths.

## Backend wiring

In `backends/__init__.py`:

- Add a `mistral` branch to `_create_backend` importing `MistralBackend`.
- Add a hint to `_unavailable_message`:
  `"Set MISTRAL_API_KEY, store the key in macOS Keychain
  (mistral/mistral-apikey), or set mistral.op_reference in config."`
- Do **not** add `mistral` to the `("gemini", "pyannote", "whisper")` tuple
  used by auto-select.

In `cli.py`:

- Add `"mistral"` to the `click.Choice` list on the `--backend` option
  (currently `src/whotalksitron/cli.py:432`). Without this change the
  Click parser rejects `--backend mistral` before `select_backend` is
  reached.

## API call

```
POST {mistral_endpoint}/audio/transcriptions
Authorization: Bearer <key>
Content-Type: multipart/form-data

  file: <audio bytes, filename = audio_path.name, mime = guessed from suffix>
  model: <mistral_model>
  timestamp_granularities: segment
```

Key contract details (verified against
`docs.mistral.ai/api/endpoint/audio/transcriptions`):

- Multipart key is `timestamp_granularities` (no `[]` suffix — that is an
  OpenAI Whisper convention).
- **Do not** send `response_format` — it is not a Mistral parameter. The
  endpoint always returns JSON.
- MIME type is derived from the file extension (reuse `_guess_mime` shape
  from `gemini.py`); default to `audio/mpeg` for unknown extensions.

Pre-flight validation in `transcribe()`:

- If `audio_path.stat().st_size == 0`, raise
  `ValueError(f"Audio file is empty: {audio_path}")`.

Read the audio bytes **once** before entering the retry envelope, so retries
do not re-read from disk and a TOCTOU window between attempts is closed:

```python
audio_bytes = audio_path.read_bytes()
def _post() -> httpx.Response:
    resp = httpx.post(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        files={"file": (audio_path.name, audio_bytes, mime)},
        data={"model": model, "timestamp_granularities": "segment"},
        timeout=600.0,
    )
    if resp.status_code == 413:
        raise _FileTooLargeError(resp)
    if resp.status_code in {400, 401, 403, 404, 422}:
        # Non-transient — do not retry.
        resp.raise_for_status()
    resp.raise_for_status()
    return resp
```

- `_FileTooLargeError` is a local exception that escapes the retry envelope
  immediately (it is **not** in `retry_on`).
- Non-transient 4xx are raised inside the closure so they propagate
  without retry; only transient codes reach `retry_with_backoff`.

Retry envelope:

```python
try:
    response = retry_with_backoff(
        _post,
        retries=3,
        base_delay=2.0,
        retry_on=(
            httpx.ConnectError,
            httpx.TimeoutException,   # parent of ReadTimeout/WriteTimeout/PoolTimeout
            _TransientHTTPError,      # 429, 5xx, 408
        ),
    )
except _FileTooLargeError as exc:
    raise RuntimeError(
        "Audio file exceeds Mistral's documented limits "
        "(max 3 hours of audio per request). Use the gemini backend, "
        "which supports large-file upload via the File API, or split "
        "the recording."
    ) from exc
except RetryExhausted as exc:
    raise RuntimeError(
        "Mistral API failed after 3 retries. Check MISTRAL_API_KEY and "
        "network connectivity, or try a different backend."
    ) from exc
```

`_TransientHTTPError` is raised inside `_post` for status codes
`{408, 429, 500, 502, 503, 504}`; on 429 it captures the `Retry-After`
header so the implementation can opt to honour it (best-effort — if
`retry_with_backoff` does not yet support per-attempt delay overrides,
log the suggested wait and proceed with the default backoff; tracked as
follow-up).

Header / logger hygiene:

- The `httpx` logger captures full request headers at DEBUG level. In
  `MistralBackend.__init__` (or at module import), set
  `logging.getLogger("httpx").setLevel(logging.WARNING)` so the bearer
  token cannot leak into a debug-enabled run. Document this in the module
  docstring.

## Response parsing

Expected JSON shape (per Mistral docs):

```json
{
  "model": "voxtral-mini-2507",
  "text": "...full transcript...",
  "language": "en",
  "segments": [
    {"start": 0.0, "end": 4.2, "text": "..."},
    ...
  ],
  "usage": {
    "prompt_audio_seconds": 203,
    "prompt_tokens": 4,
    "completion_tokens": 635,
    "total_tokens": 3264
  }
}
```

Parsing rules:

- Wrap `response.json()` in a try/except `json.JSONDecodeError`; on
  failure raise `RuntimeError` with the first 200 chars of `response.text`
  for diagnostics.
- If `segments` is a non-empty list, emit one `TranscriptSegment` per
  entry. Use defensive accessors:
  `start = float(segment.get("start", 0.0))`,
  `end = float(segment.get("end", start))`,
  `text = (segment.get("text") or "").strip()`,
  `speaker=None`. If `start > end`, log a WARNING with both values but
  keep the segment.
- If `segments` is missing or empty but `text` is non-empty, emit a single
  fallback segment with `start=0.0`, `end=0.0`, `text=text.strip()`,
  `speaker=None`, and log at INFO level: "Mistral returned no segment
  timestamps; emitting a single un-timestamped segment."
- If both are missing/empty, log a WARNING and return a result with an
  empty segment list.

`TranscriptResult.metadata`:

- `"model"`: `response_json.get("model")` (the resolved model, e.g.
  `"voxtral-mini-2507"`) or the configured `mistral_model`.
- `"backend"`: `"mistral"`.
- `"token_count"`: `response_json.get("usage", {}).get("total_tokens")`
  (may be `None` if the field is absent).
- `"prompt_audio_seconds"`:
  `response_json.get("usage", {}).get("prompt_audio_seconds")`.

## Diarization handling

`supports_diarization()` returns `False`.

When `transcribe()` is called with a non-empty `SpeakerPool`, log at INFO
level once per `MistralBackend` instance (use an instance flag
`self._diarization_notice_logged: bool` initialised in `__init__`):

> "Mistral backend ignores speaker enrollment in this version. Use the
> `gemini` or `pyannote` backend for diarization, or wait for the
> `diarize=true` integration in a future release."

Proceed normally. No error, no synthetic speaker labels.

## File size / duration handling

No client-side size check. The retry envelope short-circuits on HTTP 413
via `_FileTooLargeError` (see "API call"), and on JSON-structured size or
duration rejections returned as 400/422 the standard `raise_for_status()`
path surfaces the underlying message. We do not substring-match response
bodies.

The user-facing 413 message references Mistral's documented 3-hour
duration cap, not a numeric byte cap (the docs do not publish one).

## Progress reporting

Match the whisper backend's three-step pattern:

1. `progress.update("transcribe", 0, "sending to Mistral API")`
2. `progress.update("transcribe", 80, "parsing response")` after the POST
3. `progress.stage_complete("transcribe", f"{len(segments)} segments")`

## Testing

All HTTP interaction is mocked via `unittest.mock.patch` on the exact
import path used in the backend module (`whotalksitron.backends.mistral.httpx.post`)
to avoid namespace drift. No new pytest plugins are introduced.

### `tests/test_backends/test_mistral.py`

- `is_available()` returns `True` when `mistral_api_key` is set, `False`
  otherwise.
- `transcribe()` happy path: mock `httpx.post` to return a fixture JSON,
  assert:
  - Request URL equals `f"{endpoint.rstrip('/')}/audio/transcriptions"`.
  - `headers["Authorization"] == f"Bearer {api_key}"` (exact equality —
    catches doubled spaces / format drift).
  - Multipart `data` contains `model` and
    `timestamp_granularities == "segment"` (no `[]` suffix).
  - No `response_format` key is present.
  - Returned segments match the fixture and all have `speaker is None`.
  - `metadata["token_count"]` equals the fixture's `usage.total_tokens`.
  - `metadata["model"]` equals the resolved model from the response.
- Empty `segments` array with non-empty `text` → single fallback segment +
  INFO log captured via `caplog`.
- Missing `start`/`end` in a segment entry → defaults to `0.0`, no
  `KeyError`.
- `segment["start"] > segment["end"]` → WARNING log, segment retained.
- Non-JSON response body → `RuntimeError` with the body preview.
- `speakers` argument: passing a non-empty `SpeakerPool` logs the
  diarization-ignored INFO notice exactly once across two consecutive
  `transcribe()` calls on the same instance, and does not affect the
  request body.
- `supports_diarization()` returns `False`.
- HTTP 401 short-circuits without retry and surfaces a `RuntimeError`
  (assert `httpx.post` was called exactly once).
- HTTP 429 with `Retry-After` is retried; after `RetryExhausted` surfaces
  a `RuntimeError`.
- HTTP 413 raises the friendly "exceeds Mistral's documented limits"
  `RuntimeError` and does not retry (assert `httpx.post` was called
  exactly once).
- 0-byte audio file → `ValueError("Audio file is empty: ...")` before any
  HTTP call.
- Endpoint with trailing slash → URL is normalised, no `//audio/...` in
  the request URL.

### `tests/test_backends/test_selection.py`

- Explicit `backend = "mistral"` returns a `MistralBackend`.
- `mistral` is not picked by auto-select even when its key is the only
  one configured (auto falls through and raises
  `BackendUnavailableError`).

### `tests/test_config.py`

- `from_dict` reads the `[mistral]` table.
- `MISTRAL_API_KEY` env var overrides the file value.
- `MISTRAL_API_KEY` env var also beats a Keychain-resolved value
  (regression analogue of `test_config_env_beats_keychain`).
- `_resolve_secret` is mocked and asserted to be called twice with the
  correct keyword arguments — once with the Gemini triple, once with the
  Mistral triple. This guards the refactored signature against
  cross-backend argument leakage.
- Existing Gemini Keychain / `op` paths still pass unchanged
  (regression).
- `Config.show()` masks the Mistral key.
- `write_default` round-trips through `from_file` and emits the
  `[mistral]` table.
- `mistral_endpoint` with a non-`https://` scheme raises a clear error at
  config load.
- `mistral_endpoint` with trailing slash is normalised.

### `tests/test_cli.py`

- `--backend mistral` is accepted by Click's `Choice` validator.

## Documentation

- Update `docs/backends` to add a Mistral row with auth, diarization
  status (currently no), duration limit, and config snippet.
- Update `README.md` backend comparison table.
- Note in the README's "Secret storage" section that the `op` CLI
  (1Password) is a *runtime* dependency users must install separately,
  and that macOS Keychain resolution is darwin-only.
- Add an entry under `[Unreleased]` in `CHANGELOG.md`:
  `feat(backends): add Mistral (voxtral) transcription backend`.

## Out of scope / future work

- Wiring `diarize=true` and mapping Mistral's diarized output to the
  `SpeakerPool` enrollment flow.
- Adding `mistral` to the auto-select chain (revisit once diarization is
  wired).
- Honouring `Retry-After` precisely in `retry_with_backoff` (today we
  log the suggested delay; a follow-up should extend the retry helper
  to accept per-attempt delays).
- Streaming uploads for very large audio (today we read the whole file
  into memory once).
- Migration from the `op` CLI to the `onepassword-sdk` Python package
  once SDK adoption is feasible for all backends (unblock when Gemini
  and pyannote secret paths are also converted).
- `op_reference` syntactic validation (regex against `op://vault/item/field`)
  as defense-in-depth.
