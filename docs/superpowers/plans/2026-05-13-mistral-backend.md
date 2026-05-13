# Mistral Transcription Backend — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in `mistral` backend that calls Mistral's
`/v1/audio/transcriptions` endpoint (Voxtral Mini), with the existing
env / Keychain / `op` CLI secret-resolution pattern.

**Architecture:** New `MistralBackend` class in
`src/whotalksitron/backends/mistral.py` implementing the `Backend`
protocol. Cloud HTTP POST via `httpx` (already a dependency), bearer
auth, no diarization in this iteration. Config adds a `[mistral]` table.
`_resolve_secret` is refactored to keyword-only args so it can serve
both Gemini and Mistral without positional drift.

**Tech Stack:** Python 3.11+, `httpx`, `click`, `pytest`, `unittest.mock`.

**Reference spec:** `docs/superpowers/specs/2026-05-13-mistral-backend-design.md`

## File map

| Path | Action | Purpose |
|------|--------|---------|
| `src/whotalksitron/config.py` | modify | New `mistral_*` fields, `[mistral]` parsing, env var wiring, endpoint validation/normalisation, `_resolve_secret` refactor |
| `src/whotalksitron/backends/mistral.py` | create | `MistralBackend` class |
| `src/whotalksitron/backends/__init__.py` | modify | Register backend in `_create_backend`, add unavailable-message hint |
| `src/whotalksitron/cli.py` | modify | Add `"mistral"` to `--backend` `click.Choice` |
| `tests/test_config.py` | modify | New tests for `[mistral]`, env var, env-beats-keychain, scheme/trailing-slash, refactor-signature regression |
| `tests/test_backends/test_mistral.py` | create | Full backend test suite |
| `tests/test_backends/test_selection.py` | modify | Mistral explicit-select test, auto-select-skips-mistral test |
| `tests/test_cli.py` | modify | `--backend mistral` accepted by Click |
| `README.md` | modify | Backend comparison row |
| `docs/backends` | modify | Mistral row + config snippet |
| `CHANGELOG.md` | modify | `[Unreleased]` entry |

---

## Task 1: Add Mistral fields to `Config` dataclass `[sonnet]` `[REVIEW:light]`

**Files:**
- Modify: `src/whotalksitron/config.py:14-50` (Config dataclass)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config.py`:

```python
def test_config_has_mistral_defaults():
    cfg = Config()
    assert cfg.mistral_api_key == ""
    assert cfg.mistral_endpoint == "https://api.mistral.ai/v1"
    assert cfg.mistral_model == "voxtral-mini-latest"
    assert cfg.mistral_keychain_account == "mistral"
    assert cfg.mistral_keychain_service == "mistral-apikey"
    assert cfg.mistral_op_reference == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `just test tests/test_config.py::test_config_has_mistral_defaults`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'mistral_api_key'`.

- [ ] **Step 3: Add the fields**

In `src/whotalksitron/config.py`, immediately after the `gemini_op_reference` line in the dataclass body, add:

```python
    mistral_api_key: str = ""
    mistral_endpoint: str = "https://api.mistral.ai/v1"
    mistral_model: str = "voxtral-mini-latest"
    mistral_keychain_account: str = "mistral"
    mistral_keychain_service: str = "mistral-apikey"
    mistral_op_reference: str = ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `just test tests/test_config.py::test_config_has_mistral_defaults`
Expected: PASS.

- [ ] **Step 5: Commit `[COMMIT]`**

```bash
git add src/whotalksitron/config.py tests/test_config.py
git commit -m "feat(config): add Mistral backend fields to Config dataclass"
```

---

## Task 2: Parse `[mistral]` table in `Config.from_dict` `[sonnet]` `[REVIEW:light]`

**Files:**
- Modify: `src/whotalksitron/config.py` (`from_dict` classmethod)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
def test_config_from_dict_reads_mistral_table():
    data = {
        "mistral": {
            "api_key": "sk-test-123",
            "endpoint": "https://api.mistral.ai/v1",
            "model": "voxtral-mini-2507",
            "keychain_account": "alt-account",
            "keychain_service": "alt-service",
            "op_reference": "op://Private/mistral/key",
        }
    }
    cfg = Config.from_dict(data)
    assert cfg.mistral_api_key == "sk-test-123"
    assert cfg.mistral_model == "voxtral-mini-2507"
    assert cfg.mistral_keychain_account == "alt-account"
    assert cfg.mistral_keychain_service == "alt-service"
    assert cfg.mistral_op_reference == "op://Private/mistral/key"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `just test tests/test_config.py::test_config_from_dict_reads_mistral_table`
Expected: FAIL — assertion on `cfg.mistral_api_key`.

- [ ] **Step 3: Add parser block**

In `Config.from_dict`, after the `whisper = data.get("whisper", {})` line add:

```python
        mistral = data.get("mistral", {})
```

After the whisper parsing block (where `cfg.whisper_model = whisper["model"]` is set) add:

```python
        if "api_key" in mistral:
            cfg.mistral_api_key = mistral["api_key"]
        if "endpoint" in mistral:
            cfg.mistral_endpoint = mistral["endpoint"]
        if "model" in mistral:
            cfg.mistral_model = mistral["model"]
        if "keychain_account" in mistral:
            cfg.mistral_keychain_account = mistral["keychain_account"]
        if "keychain_service" in mistral:
            cfg.mistral_keychain_service = mistral["keychain_service"]
        if "op_reference" in mistral:
            cfg.mistral_op_reference = mistral["op_reference"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `just test tests/test_config.py::test_config_from_dict_reads_mistral_table`
Expected: PASS.

- [ ] **Step 5: Commit `[COMMIT]`**

```bash
git add src/whotalksitron/config.py tests/test_config.py
git commit -m "feat(config): parse [mistral] TOML table in from_dict"
```

---

## Task 3: Emit `[mistral]` table in `Config.write_default` and round-trip `[haiku]` `[REVIEW:light]`

**Files:**
- Modify: `src/whotalksitron/config.py` (`write_default`)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
def test_config_write_default_round_trips_mistral(tmp_path):
    cfg = Config()
    path = tmp_path / "config.toml"
    cfg.write_default(path)
    reloaded = Config.from_file(path)
    assert reloaded.mistral_model == "voxtral-mini-latest"
    assert reloaded.mistral_keychain_account == "mistral"
    assert reloaded.mistral_keychain_service == "mistral-apikey"
    assert reloaded.mistral_endpoint == "https://api.mistral.ai/v1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `just test tests/test_config.py::test_config_write_default_round_trips_mistral`
Expected: FAIL — reloaded value differs (defaults reapplied because no `[mistral]` table is written).

- [ ] **Step 3: Add `mistral` block to `write_default`**

In `Config.write_default`, inside the `data = {...}` dict, after the `"whisper": { ... }` entry add:

```python
            "mistral": {
                "api_key": "",
                "endpoint": self.mistral_endpoint,
                "model": self.mistral_model,
                "keychain_account": self.mistral_keychain_account,
                "keychain_service": self.mistral_keychain_service,
                "op_reference": "",
            },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `just test tests/test_config.py::test_config_write_default_round_trips_mistral`
Expected: PASS.

- [ ] **Step 5: Commit `[COMMIT]`**

```bash
git add src/whotalksitron/config.py tests/test_config.py
git commit -m "feat(config): emit [mistral] table in write_default"
```

---

## Task 4: Mask Mistral key in `Config.show()` `[haiku]` `[REVIEW:light]`

**Files:**
- Modify: `src/whotalksitron/config.py` (`show`)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
def test_config_show_masks_mistral_key():
    cfg = Config()
    cfg.mistral_api_key = "sk-abcdefghijklmnop"
    rendered = cfg.show()
    assert "sk-abcdefghijklmnop" not in rendered
    assert "mistral.api_key" in rendered
    assert "mistral.model" in rendered
```

- [ ] **Step 2: Run test to verify it fails**

Run: `just test tests/test_config.py::test_config_show_masks_mistral_key`
Expected: FAIL — `"mistral.api_key" in rendered` is False.

- [ ] **Step 3: Add the lines**

In `Config.show`, right before the final `return "\n".join(lines)`, add:

```python
        masked_mistral = _mask_secret(self.mistral_api_key)
        lines.append(f"mistral.api_key = {masked_mistral!r}")
        lines.append(f"mistral.endpoint = {self.mistral_endpoint!r}")
        lines.append(f"mistral.model = {self.mistral_model!r}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `just test tests/test_config.py::test_config_show_masks_mistral_key`
Expected: PASS.

- [ ] **Step 5: Commit `[COMMIT]`**

```bash
git add src/whotalksitron/config.py tests/test_config.py
git commit -m "feat(config): mask Mistral key in Config.show"
```

---

## Task 5: Refactor `_resolve_secret` to keyword-only args `[sonnet]` `[REVIEW:normal]`

This task changes a function signature used by `load_config`. Both call
sites (existing Gemini, new Mistral) use keyword arguments to prevent
positional transposition.

**Files:**
- Modify: `src/whotalksitron/config.py` (`_resolve_secret`, `load_config`)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
import inspect
from unittest.mock import patch


def test_resolve_secret_signature_is_keyword_only():
    from whotalksitron.config import _resolve_secret
    sig = inspect.signature(_resolve_secret)
    params = list(sig.parameters.values())
    names = {p.name for p in params}
    assert names == {"keychain_account", "keychain_service", "op_reference"}
    assert all(p.kind == inspect.Parameter.KEYWORD_ONLY for p in params)


def test_load_config_calls_resolve_secret_for_gemini_when_key_empty(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_API_KEY", raising=False)
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)

    config_path = tmp_path / "config.toml"
    config_path.write_text("")

    with patch("whotalksitron.config._resolve_secret", return_value=None) as m:
        load_config(config_path, {})

    # Both Gemini and Mistral keys are empty, so both should be resolved.
    assert m.call_count == 2
    calls = [c.kwargs for c in m.call_args_list]
    assert any(
        c == {
            "keychain_account": "vertex",
            "keychain_service": "vertex-apikey",
            "op_reference": "",
        }
        for c in calls
    ), calls
    assert any(
        c == {
            "keychain_account": "mistral",
            "keychain_service": "mistral-apikey",
            "op_reference": "",
        }
        for c in calls
    ), calls
```

Also add at the top of the file if not already present:
`from whotalksitron.config import Config, load_config`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `just test tests/test_config.py::test_resolve_secret_signature_is_keyword_only tests/test_config.py::test_load_config_calls_resolve_secret_for_gemini_when_key_empty`
Expected: both FAIL — signature differs, only one call site exists.

- [ ] **Step 3: Refactor `_resolve_secret`**

Replace the existing `_resolve_secret(cfg: Config) -> str | None:` with:

```python
def _resolve_secret(
    *,
    keychain_account: str,
    keychain_service: str,
    op_reference: str,
) -> str | None:
    import subprocess

    try:
        result = subprocess.run(  # noqa: S603
            [  # noqa: S607
                "security",
                "find-generic-password",
                "-a",
                keychain_account,
                "-s",
                keychain_service,
                "-w",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            logger.debug(
                "API key loaded from macOS Keychain (%s/%s)",
                keychain_service,
                keychain_account,
            )
            return result.stdout.strip()
        logger.debug(
            "Keychain lookup returned %d for %s/%s",
            result.returncode,
            keychain_service,
            keychain_account,
        )
    except FileNotFoundError:
        logger.debug("security command not found, skipping Keychain")
    except subprocess.TimeoutExpired:
        logger.debug("Keychain lookup timed out")

    if op_reference:
        try:
            result = subprocess.run(  # noqa: S603
                ["op", "read", op_reference],  # noqa: S607
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                logger.debug(
                    "API key loaded from 1Password (%s)", keychain_service
                )
                return result.stdout.strip()
            logger.debug(
                "1Password lookup returned %d (%s)",
                result.returncode,
                keychain_service,
            )
        except FileNotFoundError:
            logger.debug("op command not found, skipping 1Password")
        except subprocess.TimeoutExpired:
            logger.debug("1Password lookup timed out")

    return None
```

In `load_config`, replace the existing `if not cfg.gemini_api_key:` block with:

```python
    # Apply env vars first so they win over Keychain / 1Password.
    str_env_map = {
        "GEMINI_API_KEY": "gemini_api_key",
        "GOOGLE_CLOUD_API_KEY": "gemini_api_key",
        "GOOGLE_CLOUD_PROJECT": "gemini_project",
        "GOOGLE_CLOUD_LOCATION": "gemini_location",
        "GOOGLE_CLOUD_STORAGE_BUCKET": "gemini_gcs_bucket",
        "MISTRAL_API_KEY": "mistral_api_key",
        "WHOTALKSITRON_BACKEND": "backend",
        "WHOTALKSITRON_LOG_LEVEL": "log_level",
    }
    for env_var, attr in str_env_map.items():
        val = os.environ.get(env_var)
        if val is not None:
            if attr in {"gemini_api_key", "mistral_api_key"}:
                logger.debug("Setting %s from %s", attr, env_var)
            else:
                logger.debug("Setting %s=%s from %s", attr, val, env_var)
            setattr(cfg, attr, val)

    if not cfg.gemini_api_key:
        cfg.gemini_api_key = (
            _resolve_secret(
                keychain_account=cfg.gemini_keychain_account,
                keychain_service=cfg.gemini_keychain_service,
                op_reference=cfg.gemini_op_reference,
            )
            or ""
        )

    if not cfg.mistral_api_key:
        cfg.mistral_api_key = (
            _resolve_secret(
                keychain_account=cfg.mistral_keychain_account,
                keychain_service=cfg.mistral_keychain_service,
                op_reference=cfg.mistral_op_reference,
            )
            or ""
        )
```

Delete the old `str_env_map` block and the old single Gemini resolve call lower in the function (they're now consolidated above).

- [ ] **Step 4: Run tests to verify they pass**

Run: `just test tests/test_config.py`
Expected: all PASS, including the pre-existing Gemini Keychain / env-beats-keychain tests (regression check).

- [ ] **Step 5: Commit `[COMMIT]`**

```bash
git add src/whotalksitron/config.py tests/test_config.py
git commit -m "refactor(config): _resolve_secret takes kw-only args; resolve both backends"
```

---

## Task 6: Validate and normalise `mistral_endpoint` in `load_config` `[sonnet]` `[REVIEW:light]`

**Files:**
- Modify: `src/whotalksitron/config.py` (`load_config`)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_mistral_endpoint_rejects_http(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text('[mistral]\nendpoint = "http://insecure.example.com/v1"\n')
    with pytest.raises(ValueError, match="https://"):
        load_config(config_path, {})


def test_mistral_endpoint_strips_trailing_slash(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text('[mistral]\nendpoint = "https://api.mistral.ai/v1/"\n')
    cfg = load_config(config_path, {})
    assert cfg.mistral_endpoint == "https://api.mistral.ai/v1"


def test_mistral_endpoint_non_default_warns(tmp_path, caplog):
    config_path = tmp_path / "config.toml"
    config_path.write_text('[mistral]\nendpoint = "https://proxy.example.com/v1"\n')
    with caplog.at_level("WARNING", logger="whotalksitron.config"):
        load_config(config_path, {})
    assert any("non-default" in r.message.lower() or "endpoint" in r.message.lower()
               for r in caplog.records)
```

Make sure `import pytest` is present at the top of the test file.

- [ ] **Step 2: Run tests to verify they fail**

Run: `just test tests/test_config.py -k mistral_endpoint`
Expected: all FAIL.

- [ ] **Step 3: Add the normalisation in `load_config`**

At the very end of `load_config`, right before `return cfg`, insert:

```python
    cfg.mistral_endpoint = cfg.mistral_endpoint.rstrip("/")
    if not cfg.mistral_endpoint.startswith("https://"):
        raise ValueError(
            f"mistral.endpoint must use https:// scheme; "
            f"got {cfg.mistral_endpoint!r}"
        )
    if cfg.mistral_endpoint != "https://api.mistral.ai/v1":
        logger.warning(
            "mistral.endpoint is non-default (%s); bearer token will be "
            "sent to this host",
            cfg.mistral_endpoint,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `just test tests/test_config.py -k mistral_endpoint`
Expected: all PASS.

- [ ] **Step 5: Commit `[COMMIT]`**

```bash
git add src/whotalksitron/config.py tests/test_config.py
git commit -m "feat(config): validate and normalise mistral_endpoint"
```

---

## Task 7: `MistralBackend` skeleton — `is_available`, `supports_diarization`, `__init__` `[sonnet]` `[REVIEW:normal]`

**Files:**
- Create: `src/whotalksitron/backends/mistral.py`
- Create: `tests/test_backends/test_mistral.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_backends/test_mistral.py`:

```python
from __future__ import annotations

from whotalksitron.config import Config


def _make_config(**overrides) -> Config:
    cfg = Config()
    cfg.mistral_endpoint = "https://api.mistral.ai/v1"
    cfg.mistral_model = "voxtral-mini-latest"
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def test_backend_is_available_when_key_set():
    from whotalksitron.backends.mistral import MistralBackend
    backend = MistralBackend(_make_config(mistral_api_key="sk-test"))
    assert backend.is_available() is True


def test_backend_is_available_false_when_key_missing():
    from whotalksitron.backends.mistral import MistralBackend
    backend = MistralBackend(_make_config())
    assert backend.is_available() is False


def test_backend_name_and_diarization():
    from whotalksitron.backends.mistral import MistralBackend
    backend = MistralBackend(_make_config(mistral_api_key="sk-test"))
    assert backend.name == "mistral"
    assert backend.supports_diarization() is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `just test tests/test_backends/test_mistral.py`
Expected: FAIL — `ModuleNotFoundError: whotalksitron.backends.mistral`.

- [ ] **Step 3: Create the module**

Create `src/whotalksitron/backends/mistral.py`:

```python
"""Mistral (Voxtral) transcription backend.

Calls Mistral's /v1/audio/transcriptions endpoint. Does not perform
speaker diarization in this iteration; Mistral's `diarize=true` flag is
deferred to a future release.

Security note: this module pins the httpx logger to WARNING so the
Authorization bearer header cannot leak via debug-level logging.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from whotalksitron.config import Config
from whotalksitron.models import SpeakerPool, TranscriptResult
from whotalksitron.progress import ProgressCallback

logger = logging.getLogger(__name__)

# Prevent bearer token leakage via httpx DEBUG-level header logging.
logging.getLogger("httpx").setLevel(logging.WARNING)


class MistralBackend:
    name = "mistral"

    def __init__(self, config: Config) -> None:
        self._config = config
        self._diarization_notice_logged = False

    def is_available(self) -> bool:
        return bool(self._config.mistral_api_key)

    def supports_diarization(self) -> bool:
        return False

    def transcribe(
        self,
        audio_path: str | Path,
        *,
        speakers: SpeakerPool | None = None,
        progress: ProgressCallback | None = None,
    ) -> TranscriptResult:
        raise NotImplementedError  # filled in by later tasks
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `just test tests/test_backends/test_mistral.py`
Expected: PASS.

- [ ] **Step 5: Commit `[COMMIT]`**

```bash
git add src/whotalksitron/backends/mistral.py tests/test_backends/test_mistral.py
git commit -m "feat(backends): scaffold MistralBackend with availability check"
```

---

## Task 8: Pre-flight checks + happy-path POST `[sonnet]` `[REVIEW:normal]`

**Files:**
- Modify: `src/whotalksitron/backends/mistral.py`
- Modify: `tests/test_backends/test_mistral.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_backends/test_mistral.py`:

```python
import json
from unittest.mock import MagicMock, patch
import pytest


_HAPPY_RESPONSE = {
    "model": "voxtral-mini-2507",
    "text": "Hello world. Goodbye.",
    "language": "en",
    "segments": [
        {"start": 0.0, "end": 1.2, "text": "Hello world."},
        {"start": 1.2, "end": 2.4, "text": "Goodbye."},
    ],
    "usage": {
        "prompt_audio_seconds": 3,
        "prompt_tokens": 4,
        "completion_tokens": 5,
        "total_tokens": 9,
    },
}


def _mock_response(status_code: int = 200, body: dict | None = None,
                   text: str = "", headers: dict | None = None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.text = text or json.dumps(body or {})
    resp.json.return_value = body if body is not None else {}
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"{status_code} error", request=MagicMock(), response=resp
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


def test_transcribe_zero_byte_audio_raises(tmp_path):
    from whotalksitron.backends.mistral import MistralBackend
    audio = tmp_path / "empty.mp3"
    audio.write_bytes(b"")
    backend = MistralBackend(_make_config(mistral_api_key="sk-test"))
    with pytest.raises(ValueError, match="empty"):
        backend.transcribe(audio)


def test_transcribe_happy_path_request_shape(tmp_path):
    from whotalksitron.backends.mistral import MistralBackend
    audio = tmp_path / "clip.mp3"
    audio.write_bytes(b"fake-audio-bytes")
    backend = MistralBackend(_make_config(mistral_api_key="sk-test"))

    with patch(
        "whotalksitron.backends.mistral.httpx.post",
        return_value=_mock_response(200, _HAPPY_RESPONSE),
    ) as post:
        result = backend.transcribe(audio)

    assert post.call_count == 1
    args, kwargs = post.call_args
    assert args[0] == "https://api.mistral.ai/v1/audio/transcriptions"
    assert kwargs["headers"] == {"Authorization": "Bearer sk-test"}
    assert kwargs["data"] == {
        "model": "voxtral-mini-latest",
        "timestamp_granularities": "segment",
    }
    assert "response_format" not in kwargs["data"]
    file_field = kwargs["files"]["file"]
    assert file_field[0] == "clip.mp3"
    assert file_field[1] == b"fake-audio-bytes"
    assert kwargs["timeout"] == 600.0
    assert len(result.segments) == 2
    assert result.segments[0].text == "Hello world."
    assert all(s.speaker is None for s in result.segments)
    assert result.metadata["backend"] == "mistral"
    assert result.metadata["model"] == "voxtral-mini-2507"
    assert result.metadata["token_count"] == 9
    assert result.metadata["prompt_audio_seconds"] == 3


def test_transcribe_strips_trailing_slash_in_url(tmp_path):
    from whotalksitron.backends.mistral import MistralBackend
    audio = tmp_path / "clip.mp3"
    audio.write_bytes(b"x")
    # Config.load_config normally strips this; sanity-check the backend
    # doesn't accidentally re-introduce a double slash.
    backend = MistralBackend(_make_config(
        mistral_api_key="sk-test",
        mistral_endpoint="https://api.mistral.ai/v1",
    ))
    with patch(
        "whotalksitron.backends.mistral.httpx.post",
        return_value=_mock_response(200, _HAPPY_RESPONSE),
    ) as post:
        backend.transcribe(audio)
    assert post.call_args[0][0] == "https://api.mistral.ai/v1/audio/transcriptions"
    assert "//audio" not in post.call_args[0][0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `just test tests/test_backends/test_mistral.py`
Expected: FAIL — `NotImplementedError`.

- [ ] **Step 3: Implement `transcribe` happy path**

In `src/whotalksitron/backends/mistral.py`, replace the `transcribe` stub with:

```python
    def transcribe(
        self,
        audio_path: str | Path,
        *,
        speakers: SpeakerPool | None = None,
        progress: ProgressCallback | None = None,
    ) -> TranscriptResult:
        from whotalksitron.models import TranscriptResult, TranscriptSegment

        audio_path = Path(audio_path)
        if audio_path.stat().st_size == 0:
            raise ValueError(f"Audio file is empty: {audio_path}")

        if speakers and speakers.speakers and not self._diarization_notice_logged:
            logger.info(
                "Mistral backend ignores speaker enrollment in this version. "
                "Use the gemini or pyannote backend for diarization."
            )
            self._diarization_notice_logged = True

        if progress:
            progress.update("transcribe", 0, "sending to Mistral API")

        endpoint = self._config.mistral_endpoint.rstrip("/")
        url = f"{endpoint}/audio/transcriptions"
        mime = _guess_mime(audio_path)
        audio_bytes = audio_path.read_bytes()

        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {self._config.mistral_api_key}"},
            files={"file": (audio_path.name, audio_bytes, mime)},
            data={
                "model": self._config.mistral_model,
                "timestamp_granularities": "segment",
            },
            timeout=600.0,
        )
        response.raise_for_status()

        if progress:
            progress.update("transcribe", 80, "parsing response")

        data = response.json()
        segments = [
            TranscriptSegment(
                start=float(seg.get("start", 0.0)),
                end=float(seg.get("end", seg.get("start", 0.0))),
                text=(seg.get("text") or "").strip(),
                speaker=None,
            )
            for seg in data.get("segments") or []
        ]

        usage = data.get("usage") or {}
        result = TranscriptResult(
            segments=segments,
            metadata={
                "backend": "mistral",
                "model": data.get("model") or self._config.mistral_model,
                "token_count": usage.get("total_tokens"),
                "prompt_audio_seconds": usage.get("prompt_audio_seconds"),
            },
        )

        if progress:
            progress.stage_complete("transcribe", f"{len(segments)} segments")
        return result


def _guess_mime(path: Path) -> str:
    return {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".flac": "audio/flac",
        ".ogg": "audio/ogg",
        ".m4a": "audio/mp4",
        ".webm": "audio/webm",
    }.get(path.suffix.lower(), "audio/mpeg")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `just test tests/test_backends/test_mistral.py`
Expected: all PASS.

- [ ] **Step 5: Commit `[COMMIT]`**

```bash
git add src/whotalksitron/backends/mistral.py tests/test_backends/test_mistral.py
git commit -m "feat(backends): MistralBackend happy-path transcribe with usage metadata"
```

---

## Task 9: Response parsing edge cases (empty segments, missing fields, JSON failure) `[sonnet]` `[REVIEW:normal]`

**Files:**
- Modify: `src/whotalksitron/backends/mistral.py`
- Modify: `tests/test_backends/test_mistral.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_transcribe_empty_segments_fallback(tmp_path, caplog):
    from whotalksitron.backends.mistral import MistralBackend
    audio = tmp_path / "clip.mp3"
    audio.write_bytes(b"x")
    backend = MistralBackend(_make_config(mistral_api_key="sk-test"))
    body = {"model": "voxtral-mini-2507", "text": "Single chunk.", "segments": []}
    with patch(
        "whotalksitron.backends.mistral.httpx.post",
        return_value=_mock_response(200, body),
    ), caplog.at_level("INFO", logger="whotalksitron.backends.mistral"):
        result = backend.transcribe(audio)
    assert len(result.segments) == 1
    assert result.segments[0].text == "Single chunk."
    assert result.segments[0].start == 0.0
    assert result.segments[0].end == 0.0
    assert any("no segment timestamps" in r.message.lower() for r in caplog.records)


def test_transcribe_missing_start_end_defaults_to_zero(tmp_path):
    from whotalksitron.backends.mistral import MistralBackend
    audio = tmp_path / "clip.mp3"
    audio.write_bytes(b"x")
    backend = MistralBackend(_make_config(mistral_api_key="sk-test"))
    body = {"text": "x", "segments": [{"text": "no times"}]}
    with patch(
        "whotalksitron.backends.mistral.httpx.post",
        return_value=_mock_response(200, body),
    ):
        result = backend.transcribe(audio)
    assert result.segments[0].start == 0.0
    assert result.segments[0].end == 0.0
    assert result.segments[0].text == "no times"


def test_transcribe_inverted_segment_warns_but_keeps(tmp_path, caplog):
    from whotalksitron.backends.mistral import MistralBackend
    audio = tmp_path / "clip.mp3"
    audio.write_bytes(b"x")
    backend = MistralBackend(_make_config(mistral_api_key="sk-test"))
    body = {"segments": [{"start": 5.0, "end": 2.0, "text": "bad"}]}
    with patch(
        "whotalksitron.backends.mistral.httpx.post",
        return_value=_mock_response(200, body),
    ), caplog.at_level("WARNING", logger="whotalksitron.backends.mistral"):
        result = backend.transcribe(audio)
    assert len(result.segments) == 1
    assert any("start" in r.message.lower() and "end" in r.message.lower()
               for r in caplog.records)


def test_transcribe_non_json_response_raises_runtime_error(tmp_path):
    from whotalksitron.backends.mistral import MistralBackend
    audio = tmp_path / "clip.mp3"
    audio.write_bytes(b"x")
    backend = MistralBackend(_make_config(mistral_api_key="sk-test"))
    resp = _mock_response(200, body=None, text="<html>502 Bad Gateway</html>")
    resp.json.side_effect = json.JSONDecodeError("bad", "doc", 0)
    with patch("whotalksitron.backends.mistral.httpx.post", return_value=resp):
        with pytest.raises(RuntimeError, match="parse"):
            backend.transcribe(audio)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `just test tests/test_backends/test_mistral.py`
Expected: FAIL on the four new tests.

- [ ] **Step 3: Implement the parsing branches**

In `src/whotalksitron/backends/mistral.py`, replace the JSON-parsing block (everything from `data = response.json()` through `result = TranscriptResult(...)`) with:

```python
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            preview = response.text[:200]
            raise RuntimeError(
                f"Could not parse Mistral response as JSON: {preview!r}"
            ) from exc

        raw_segments = data.get("segments") or []
        segments: list[TranscriptSegment] = []
        for seg in raw_segments:
            start = float(seg.get("start", 0.0))
            end = float(seg.get("end", start))
            if start > end:
                logger.warning(
                    "Mistral segment has start>end (start=%s, end=%s); keeping as-is",
                    start,
                    end,
                )
            segments.append(
                TranscriptSegment(
                    start=start,
                    end=end,
                    text=(seg.get("text") or "").strip(),
                    speaker=None,
                )
            )

        if not segments:
            text = (data.get("text") or "").strip()
            if text:
                logger.info(
                    "Mistral returned no segment timestamps; "
                    "emitting a single un-timestamped segment."
                )
                segments.append(
                    TranscriptSegment(start=0.0, end=0.0, text=text, speaker=None)
                )
            else:
                logger.warning("Mistral returned empty transcript")

        usage = data.get("usage") or {}
        result = TranscriptResult(
            segments=segments,
            metadata={
                "backend": "mistral",
                "model": data.get("model") or self._config.mistral_model,
                "token_count": usage.get("total_tokens"),
                "prompt_audio_seconds": usage.get("prompt_audio_seconds"),
            },
        )
```

Add `import json` at the top of the module if not already present.

- [ ] **Step 4: Run tests to verify they pass**

Run: `just test tests/test_backends/test_mistral.py`
Expected: all PASS.

- [ ] **Step 5: Commit `[COMMIT]`**

```bash
git add src/whotalksitron/backends/mistral.py tests/test_backends/test_mistral.py
git commit -m "feat(backends): handle Mistral response edge cases (empty/inverted/non-JSON)"
```

---

## Task 10: Error handling — 413 short-circuit, non-transient 4xx, retry envelope `[sonnet]` `[REVIEW:full]`

This task adds the typed local exceptions and the retry envelope. After
this task, all error paths from the spec are implemented.

**Files:**
- Modify: `src/whotalksitron/backends/mistral.py`
- Modify: `tests/test_backends/test_mistral.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_transcribe_413_friendly_error_no_retry(tmp_path):
    from whotalksitron.backends.mistral import MistralBackend
    audio = tmp_path / "clip.mp3"
    audio.write_bytes(b"x")
    backend = MistralBackend(_make_config(mistral_api_key="sk-test"))
    with patch(
        "whotalksitron.backends.mistral.httpx.post",
        return_value=_mock_response(413, body={"error": "too large"}),
    ) as post:
        with pytest.raises(RuntimeError, match="3 hours"):
            backend.transcribe(audio)
    assert post.call_count == 1  # No retry.


def test_transcribe_401_no_retry(tmp_path):
    from whotalksitron.backends.mistral import MistralBackend
    audio = tmp_path / "clip.mp3"
    audio.write_bytes(b"x")
    backend = MistralBackend(_make_config(mistral_api_key="sk-bad"))
    with patch(
        "whotalksitron.backends.mistral.httpx.post",
        return_value=_mock_response(401, body={"error": "unauthorized"}),
    ) as post:
        with pytest.raises(RuntimeError):
            backend.transcribe(audio)
    assert post.call_count == 1


def test_transcribe_429_retries_then_fails(tmp_path):
    from whotalksitron.backends.mistral import MistralBackend
    audio = tmp_path / "clip.mp3"
    audio.write_bytes(b"x")
    backend = MistralBackend(_make_config(mistral_api_key="sk-test"))
    with patch(
        "whotalksitron.backends.mistral.httpx.post",
        return_value=_mock_response(429, body={"error": "rate limited"},
                                    headers={"Retry-After": "1"}),
    ) as post, patch("whotalksitron.backends.mistral.time.sleep"):
        with pytest.raises(RuntimeError, match="3 retries"):
            backend.transcribe(audio)
    assert post.call_count == 4  # initial + 3 retries.


def test_transcribe_500_retries_then_recovers(tmp_path):
    from whotalksitron.backends.mistral import MistralBackend
    audio = tmp_path / "clip.mp3"
    audio.write_bytes(b"x")
    backend = MistralBackend(_make_config(mistral_api_key="sk-test"))
    responses = [
        _mock_response(500, body={"error": "boom"}),
        _mock_response(200, _HAPPY_RESPONSE),
    ]
    with patch(
        "whotalksitron.backends.mistral.httpx.post",
        side_effect=responses,
    ), patch("whotalksitron.backends.mistral.time.sleep"):
        result = backend.transcribe(audio)
    assert len(result.segments) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `just test tests/test_backends/test_mistral.py -k "413 or 401 or 429 or 500"`
Expected: FAIL — current code raises `HTTPStatusError`, not the friendly messages, and does not retry.

- [ ] **Step 3: Add typed exceptions and rewrite the POST flow**

In `src/whotalksitron/backends/mistral.py`, add near the top of the module (after `logger = ...`):

```python
import time

from whotalksitron.retry import RetryExhausted, retry_with_backoff


_TRANSIENT_STATUS = {408, 429, 500, 502, 503, 504}


class _FileTooLargeError(Exception):
    pass


class _TransientHTTPError(Exception):
    def __init__(self, status_code: int, retry_after: float | None = None) -> None:
        super().__init__(f"transient http {status_code}")
        self.status_code = status_code
        self.retry_after = retry_after
```

In `transcribe`, replace the single `httpx.post(...)` / `raise_for_status()` block with this retry-wrapped flow:

```python
        def _post() -> httpx.Response:
            resp = httpx.post(
                url,
                headers={"Authorization": f"Bearer {self._config.mistral_api_key}"},
                files={"file": (audio_path.name, audio_bytes, mime)},
                data={
                    "model": self._config.mistral_model,
                    "timestamp_granularities": "segment",
                },
                timeout=600.0,
            )
            if resp.status_code == 413:
                raise _FileTooLargeError()
            if resp.status_code in _TRANSIENT_STATUS:
                retry_after_hdr = resp.headers.get("Retry-After") if resp.headers else None
                try:
                    retry_after = float(retry_after_hdr) if retry_after_hdr else None
                except ValueError:
                    retry_after = None
                if retry_after:
                    logger.info(
                        "Mistral asked us to retry after %.1fs (current backoff "
                        "policy will use its own delay)",
                        retry_after,
                    )
                raise _TransientHTTPError(resp.status_code, retry_after)
            resp.raise_for_status()
            return resp

        try:
            response = retry_with_backoff(
                _post,
                retries=3,
                base_delay=2.0,
                retry_on=(
                    httpx.ConnectError,
                    httpx.TimeoutException,
                    _TransientHTTPError,
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
                "Mistral API failed after 3 retries. Check MISTRAL_API_KEY "
                "and network connectivity, or try a different backend."
            ) from exc
        except httpx.HTTPStatusError as exc:
            # Non-transient 4xx (e.g. 401 unauthorized).
            raise RuntimeError(
                f"Mistral API rejected the request "
                f"(HTTP {exc.response.status_code}). Check your API key and "
                f"request parameters."
            ) from exc
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `just test tests/test_backends/test_mistral.py`
Expected: all PASS.

- [ ] **Step 5: Commit `[COMMIT]`**

```bash
git add src/whotalksitron/backends/mistral.py tests/test_backends/test_mistral.py
git commit -m "feat(backends): Mistral retry envelope with 413/401 short-circuit"
```

---

## Task 11: Diarization-notice once-per-instance test `[haiku]` `[REVIEW:light]`

**Files:**
- Modify: `tests/test_backends/test_mistral.py`

- [ ] **Step 1: Write the failing test**

```python
def test_transcribe_diarization_notice_logged_once_per_instance(tmp_path, caplog):
    from whotalksitron.backends.mistral import MistralBackend
    from whotalksitron.models import SpeakerPool

    audio = tmp_path / "clip.mp3"
    audio.write_bytes(b"x")
    backend = MistralBackend(_make_config(mistral_api_key="sk-test"))
    pool = SpeakerPool(speakers={"Alice": [tmp_path / "alice.wav"]})

    with patch(
        "whotalksitron.backends.mistral.httpx.post",
        return_value=_mock_response(200, _HAPPY_RESPONSE),
    ), caplog.at_level("INFO", logger="whotalksitron.backends.mistral"):
        backend.transcribe(audio, speakers=pool)
        backend.transcribe(audio, speakers=pool)

    notices = [r for r in caplog.records
               if "ignores speaker enrollment" in r.message]
    assert len(notices) == 1
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `just test tests/test_backends/test_mistral.py::test_transcribe_diarization_notice_logged_once_per_instance`
Expected: PASS if the flag is correctly set in Task 8; FAIL if it logs twice. Either way fix the implementation if needed (the existing implementation from Task 8 sets `self._diarization_notice_logged = True`, which should already satisfy this test).

- [ ] **Step 3: Commit `[COMMIT]`**

If implementation was already correct:

```bash
git add tests/test_backends/test_mistral.py
git commit -m "test(backends): assert Mistral diarization notice logs once per instance"
```

---

## Task 12: Wire Mistral into `_create_backend` and `_unavailable_message` `[sonnet]` `[REVIEW:light]`

**Files:**
- Modify: `src/whotalksitron/backends/__init__.py`
- Modify: `tests/test_backends/test_selection.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_backends/test_selection.py`:

```python
def test_select_backend_explicit_mistral():
    from whotalksitron.backends import select_backend
    from whotalksitron.backends.mistral import MistralBackend
    from whotalksitron.config import Config

    cfg = Config()
    cfg.backend = "mistral"
    cfg.mistral_api_key = "sk-test"
    backend = select_backend(cfg)
    assert isinstance(backend, MistralBackend)


def test_select_backend_mistral_unavailable_when_no_key():
    from whotalksitron.backends import BackendUnavailableError, select_backend
    from whotalksitron.config import Config
    import pytest

    cfg = Config()
    cfg.backend = "mistral"
    with pytest.raises(BackendUnavailableError, match="MISTRAL_API_KEY"):
        select_backend(cfg)


def test_auto_select_does_not_pick_mistral(monkeypatch):
    """Even when Mistral is the only configured backend, auto must skip it."""
    from whotalksitron.backends import BackendUnavailableError, select_backend
    from whotalksitron.config import Config
    import pytest

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_API_KEY", raising=False)
    cfg = Config()
    cfg.backend = "auto"
    cfg.mistral_api_key = "sk-test"
    # No gemini/pyannote/whisper available; mistral is opt-in only.
    with pytest.raises(BackendUnavailableError):
        select_backend(cfg)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `just test tests/test_backends/test_selection.py`
Expected: first two FAIL (mistral not in `_create_backend`); third PASS by accident (auto loop already excludes mistral) but rerun after the wiring change.

- [ ] **Step 3: Update `_create_backend` and `_unavailable_message`**

In `src/whotalksitron/backends/__init__.py`, in `_create_backend`, add a new `elif` branch before the `else`:

```python
    elif name == "mistral":
        from whotalksitron.backends.mistral import MistralBackend

        return MistralBackend(config)
```

In `_unavailable_message`, extend the `hints` dict:

```python
        "mistral": "Set MISTRAL_API_KEY, store the key in macOS Keychain "
        "(mistral/mistral-apikey), or set mistral.op_reference in config.",
```

**Do not** add `"mistral"` to the auto-select tuple — that's intentional.

- [ ] **Step 4: Run tests to verify they pass**

Run: `just test tests/test_backends/test_selection.py`
Expected: all PASS.

- [ ] **Step 5: Commit `[COMMIT]`**

```bash
git add src/whotalksitron/backends/__init__.py tests/test_backends/test_selection.py
git commit -m "feat(backends): register mistral in _create_backend and hints"
```

---

## Task 13: Add `"mistral"` to the CLI `--backend` Choice `[haiku]` `[REVIEW:light]`

**Files:**
- Modify: `src/whotalksitron/cli.py:432`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_cli_accepts_backend_mistral():
    from click.testing import CliRunner
    from whotalksitron.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["--backend", "mistral", "--help"])
    # `--help` short-circuits before any audio processing. The point is
    # that Click's Choice validator must accept "mistral".
    assert result.exit_code == 0, result.output
    assert "Invalid value for '--backend'" not in result.output
```

(If the existing `test_cli.py` uses a different entry-point name, mirror its pattern.)

- [ ] **Step 2: Run test to verify it fails**

Run: `just test tests/test_cli.py::test_cli_accepts_backend_mistral`
Expected: FAIL — `Invalid value for '--backend'`.

- [ ] **Step 3: Update the Choice list**

In `src/whotalksitron/cli.py:432`, change:

```python
@click.option("--backend", type=click.Choice(["gemini", "pyannote", "whisper"]))
```

to:

```python
@click.option("--backend", type=click.Choice(["gemini", "pyannote", "whisper", "mistral"]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `just test tests/test_cli.py::test_cli_accepts_backend_mistral`
Expected: PASS.

- [ ] **Step 5: Commit `[COMMIT]`**

```bash
git add src/whotalksitron/cli.py tests/test_cli.py
git commit -m "feat(cli): accept --backend mistral"
```

---

## Task 14: Documentation — README, docs/backends, CHANGELOG `[haiku]` `[REVIEW:light]`

**Files:**
- Modify: `README.md`
- Modify: `docs/backends`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update README backend table**

In `README.md`, find the existing backend comparison table (search for `gemini` and `pyannote`) and add a `mistral` row matching the existing table format. Cell values:

- Name: `mistral`
- Provider: Mistral (Voxtral)
- Auth: `MISTRAL_API_KEY` env var, macOS Keychain (`mistral/mistral-apikey`), or `op` 1Password reference
- Diarization: No (deferred)
- Notes: Cloud, up to 3-hour audio per request; opt-in only (not in auto-select)

Also append a sentence to the "Secret storage" section (or create one) noting:

> The `op` CLI (1Password) and `security` (macOS Keychain) commands are
> runtime dependencies users install separately. Keychain resolution is
> macOS-only; on other platforms, use `MISTRAL_API_KEY` or
> `mistral.op_reference`.

- [ ] **Step 2: Update `docs/backends`**

Add a section after the existing `whisper` section:

```markdown
### mistral (Voxtral Mini)

Cloud transcription via Mistral's `/v1/audio/transcriptions` endpoint.

**Auth:** Set `MISTRAL_API_KEY` in the environment, store the key in
macOS Keychain under service `mistral-apikey` account `mistral`, or set
`mistral.op_reference` to a 1Password `op://...` reference in config.

**Diarization:** Not supported in this version. Use `gemini` or
`pyannote` for diarization.

**Limits:** Up to 3 hours of audio per request (Mistral-documented).

**Config snippet:**

\`\`\`toml
[defaults]
backend = "mistral"

[mistral]
model = "voxtral-mini-latest"
# api_key = ""           # leave blank to use env/keychain/1password
# op_reference = "op://Private/mistral/api_key"
\`\`\`

Mistral is **not** in the auto-select fallback chain — you must pick it
explicitly.
```

- [ ] **Step 3: Add CHANGELOG entry**

In `CHANGELOG.md`, add under `## [Unreleased]` (create the section if absent):

```markdown
### Added
- New `mistral` backend (Voxtral Mini) for cloud transcription via
  Mistral's `/v1/audio/transcriptions` endpoint. Opt-in via
  `--backend mistral`. Supports `MISTRAL_API_KEY`, macOS Keychain, and
  1Password (`op` CLI) for secret resolution.
```

- [ ] **Step 4: Commit `[COMMIT]`**

```bash
git add README.md docs/backends CHANGELOG.md
git commit -m "docs: document mistral transcription backend"
```

---

## Task 15: Final CI sweep `[haiku]` `[REVIEW:normal]`

**Files:** none (verification only)

- [ ] **Step 1: Run the sandbox CI suite**

Run: `just ensureci-sandbox`
Expected: all green (`just lint`, `just fmt --check`, `just test`, `just secaudit`).

- [ ] **Step 2: If anything fails, fix the underlying issue and re-run**

Do not paper over with `--no-verify` or by suppressing warnings. If lint
flags something genuinely unfixable, surface it in the next turn instead
of committing.

- [ ] **Step 3: Final commit only if changes were needed `[COMMIT]`**

```bash
git add <changed files>
git commit -m "chore: post-implementation CI fixups"
```

---

## Adversarial review checkpoint `[REVIEW:full]`

After Task 10 (retry envelope) lands, dispatch an adversarial review
across these lenses before continuing to Tasks 11–15:

- **API contract** — re-verify request shape against a live Mistral docs
  fetch. The implementation should not have re-introduced
  `response_format` or `timestamp_granularities[]`.
- **Security** — confirm the bearer token is not in any test fixture
  log capture, and that the `httpx` logger pin actually applies.
- **Error handling** — confirm 401 / 413 / 429 / 5xx paths in the test
  suite exercise the exact branches in the implementation.

If the review surfaces criticals, pause Tasks 11–15 and revise.

---

## Self-review (writing-plans)

- **Spec coverage:** every section of the design doc is mapped to at
  least one task (config fields → T1-T4, secret refactor → T5, endpoint
  validation → T6, backend skeleton → T7, happy path → T8, parsing edge
  cases → T9, error envelope → T10, diarization notice → T11, selection
  wiring → T12, CLI → T13, docs → T14, CI → T15).
- **No placeholders:** every code step shows the actual code to write.
- **Type consistency:** `MistralBackend.__init__`, `is_available`,
  `supports_diarization`, `transcribe`, `_diarization_notice_logged`,
  `_FileTooLargeError`, `_TransientHTTPError`, `_TRANSIENT_STATUS`,
  `_guess_mime` are all introduced once and referenced with the same
  names downstream.
- **Test-first ordering:** every task writes the failing test before
  the implementation.
