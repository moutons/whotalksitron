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
│       ├── backends/
│       │   ├── __init__.py     # Backend protocol, auto-selection
│       │   ├── gemini.py
│       │   ├── pyannote.py
│       │   └── whisper.py
│       └── speakers/
│           ├── __init__.py
│           ├── enrollment.py   # enroll, import, list, extract
│           ├── matching.py     # voiceprint comparison
│           └── embeddings.py   # embedding computation
└── tests/
    ├── conftest.py
    ├── test_cli.py
    ├── test_config.py
    ├── test_pipeline.py
    ├── test_output.py
    ├── test_backends/
    │   ├── test_gemini.py
    │   ├── test_pyannote.py
    │   └── test_whisper.py
    └── test_speakers/
        ├── test_enrollment.py
        ├── test_matching.py
        └── test_embeddings.py
```

## Dependencies

```toml
[project]
dependencies = [
    "click",
    "tomli",          # TOML parsing (Python <3.11)
    "tomli-w",        # TOML writing
    "google-genai",   # Gemini SDK
    "numpy",          # embeddings
]

[project.optional-dependencies]
local = [
    "torch",
    "torchaudio",
    "pyannote.audio",
    "openai-whisper",
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
