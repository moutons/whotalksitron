# Packaging & Installation

## Project Structure

```
whotalksitron/
├── pyproject.toml
├── src/
│   └── whotalksitron/
│       ├── __init__.py
│       ├── cli.py              # click entry point
│       ├── config.py           # config loading, precedence
│       ├── pipeline.py         # orchestrates the 6-stage flow
│       ├── models.py           # TranscriptSegment, TranscriptResult, SpeakerPool
│       ├── output.py           # markdown renderer
│       ├── progress.py         # JSON progress reporting to stderr
│       ├── retry.py            # exponential backoff for API calls
│       ├── backends/
│       │   ├── __init__.py     # Backend protocol, auto-selection
│       │   ├── gemini.py
│       │   ├── pyannote.py
│       │   └── whisper.py
│       └── speakers/
│           ├── __init__.py
│           ├── enrollment.py   # enroll, import, list, extract
│           ├── matching.py     # voiceprint comparison
│           ├── embeddings.py   # embedding computation
│           └── extraction.py   # sample extraction from transcripts
└── tests/
    ├── conftest.py
    ├── test_cli.py
    ├── test_config.py
    ├── test_retry.py
    ├── test_pipeline.py
    ├── test_output.py
    ├── test_backends/
    │   ├── test_gemini.py
    │   ├── test_pyannote.py
    │   └── test_whisper.py
    └── test_speakers/
        ├── test_enrollment.py
        ├── test_matching.py
        ├── test_embeddings.py
        └── test_extraction.py
```

## Dependencies

```toml
[project]
requires-python = ">=3.11"
dependencies = [
    "click",
    "tomli-w",        # TOML writing (tomllib is stdlib in 3.11+)
    "google-genai",   # Gemini SDK
    "numpy",          # embeddings
    "httpx",          # Ollama/LM Studio API client
]

[project.optional-dependencies]
local = [
    "torch",
    "torchaudio",
    "pyannote.audio",
    "faster-whisper",
]
```

## Entry Point

```toml
[project.scripts]
whotalksitron = "whotalksitron.cli:main"
```

## Installation

| Scenario | Command |
|---|---|
| Gemini-only (lean) | `uv tool install whotalksitron` |
| Full local backends | `uv tool install whotalksitron --with local` |
| Development | `uv sync --all-extras` |

`uv tool install` places the binary in `~/.local/bin/`. No manual symlink to `~/bin/` needed if `~/.local/bin/` is on PATH.

## Tooling

Per project conventions:

- **Package manager:** uv
- **Linter:** ruff
- **Type checker:** ty
- **Formatter:** ruff format
- **Test runner:** pytest (via `just test`)
