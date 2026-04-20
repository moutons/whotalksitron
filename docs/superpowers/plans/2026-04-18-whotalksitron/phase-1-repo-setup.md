# Phase 1: Repository Setup

Customize the repo template for a Python project. After this phase, `just test`, `just lint`, `just fmt`, and `just ensureci-sandbox` all work, and the project is installable via `uv sync`.

---

### Task 1: Set up repository for Python `[haiku]`

**Files:**
- Create: `pyproject.toml`
- Create: `src/whotalksitron/__init__.py`
- Modify: `justfile`
- Modify: `README.md`
- Modify: `.forgejo/workflows/ci.yml`
- Modify: `lefthook.yml`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "whotalksitron"
version = "0.1.0"
description = "Audio transcription CLI with speaker identification"
requires-python = ">=3.11"
license = "Apache-2.0"
authors = [
    { name = "Shaun Mouton", email = "shaun.mouton@icloud.com" },
]
dependencies = [
    "click>=8.1,<9",
    "tomli-w>=1.0,<2",
    "google-genai>=1.0,<2",
    "numpy>=1.26,<3",
    "httpx>=0.27,<1",
]

[project.optional-dependencies]
local = [
    "torch>=2.2,<3",
    "torchaudio>=2.2,<3",
    "pyannote.audio>=3.1,<4",
    "faster-whisper>=1.1,<2",
]
dev = [
    "pytest>=8.0,<9",
    "pytest-cov>=5.0,<6",
    "ruff>=0.8,<1",
]

[project.scripts]
whotalksitron = "whotalksitron.cli:main"

[tool.ruff]
target-version = "py311"
src = ["src"]

[tool.ruff.lint]
select = ["E", "F", "I", "S", "UP", "B", "SIM", "RUF"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.hatch.build.targets.wheel]
packages = ["src/whotalksitron"]
```

- [ ] **Step 2: Create the package init file**

Create `src/whotalksitron/__init__.py`:

```python
"""Audio transcription CLI with speaker identification."""

__version__ = "0.1.0"
```

- [ ] **Step 3: Create a minimal CLI entry point**

Create `src/whotalksitron/cli.py`:

```python
import click

@click.group()
@click.version_option(package_name="whotalksitron")
def main() -> None:
    """Audio transcription CLI with speaker identification."""

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Create the test directory with a smoke test**

Create `tests/__init__.py` (empty file).

Create `tests/conftest.py`:

```python
"""Shared test fixtures for whotalksitron."""
```

Create `tests/test_cli.py`:

```python
from click.testing import CliRunner

from whotalksitron.cli import main


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "Audio transcription CLI" in result.output


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output
```

- [ ] **Step 5: Replace the justfile with Python recipes**

Replace the entire `justfile` with:

```just
# Default recipe: show available recipes
default:
    @just --list

# Run all tests
test: _ci_testcover

# Run linter(s)
lint: _ci_lint

# Auto-format code
fmt:
    uv run ruff format .
    uv run ruff check --fix .

# Security audit (gitleaks + ruff security rules)
secaudit: _ci_secaudit
    gitleaks git --platform gitea .

# Full CI simulation
ensureci: _ci_mdlint _ci_lint _ci_fmtcheck _ci_vulncheck _ci_secaudit _ci_typecheck _ci_testcover
    @echo "All CI checks passed!"

# Sandbox-safe CI (no TLS-dependent checks)
ensureci-sandbox: _ci_mdlint _ci_lint _ci_fmtcheck _ci_secaudit _ci_typecheck _ci_testcover
    @echo "All sandbox-compatible CI checks passed! (vulncheck skipped)"

# Quick validation
isgreen: fmt lint test

# Remove build artifacts
clean:
    rm -rf dist/ build/ .ruff_cache/ .pytest_cache/ htmlcov/
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    find . -name "*.pyc" -delete 2>/dev/null || true

# --- CI sub-recipes (hidden from `just --list`) ---

_ci_mdlint:
    npx --yes markdownlint-cli2 "**/*.md" "#node_modules"

_ci_lint:
    uv run ruff check .

_ci_fmtcheck:
    uv run ruff format --check .

_ci_vulncheck:
    @echo "_ci_vulncheck: not yet configured (requires network)"

_ci_secaudit:
    uv run ruff check --select S .

_ci_typecheck:
    uv run ty check

_ci_testcover:
    uv run pytest --cov=whotalksitron --cov-report=term-missing
```

- [ ] **Step 6: Update the CI workflow for Python + uv**

Replace `.forgejo/workflows/ci.yml` with:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  ci:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2

      - name: Install just 1.40.0
        run: |
          mkdir -p "$HOME/.local/bin"
          curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --tag 1.40.0 --to "$HOME/.local/bin"
          echo "$HOME/.local/bin" >> "$GITHUB_PATH"

      - name: Install uv 0.6.14
        run: |
          curl -LsSf https://astral.sh/uv/0.6.14/install.sh | sh
          echo "$HOME/.local/bin" >> "$GITHUB_PATH"

      - name: Set up Python
        run: uv python install 3.11

      - name: Install dependencies
        run: uv sync --group dev

      - name: Run CI checks
        run: just ensureci
```

- [ ] **Step 7: Update lefthook.yml**

Replace `lefthook.yml` with:

```yaml
pre-commit:
  commands:
    check-env:
      run: |
        missing=""
        [ -z "$CLAUDEBOT_EMAIL" ] && missing="$missing CLAUDEBOT_EMAIL"
        [ -z "$CLAUDEBOT_FJ_TOKEN" ] && missing="$missing CLAUDEBOT_FJ_TOKEN"
        if [ -n "$missing" ]; then
          echo "ERROR: required env vars not set:$missing"
          echo "See README.md for setup instructions."
          exit 1
        fi
    mdlint:
      run: just _ci_mdlint
    fmtcheck:
      run: just _ci_fmtcheck

pre-push:
  commands:
    ensureci-sandbox:
      run: just ensureci-sandbox
```

No changes needed — the existing lefthook already calls `just _ci_fmtcheck` and `just ensureci-sandbox`, which now invoke the Python-specific recipes.

- [ ] **Step 8: Replace README.md**

```markdown
# whotalksitron

Audio transcription CLI with speaker identification. Accepts audio files, produces markdown transcripts with speaker-attributed segments and timestamps.

## Features

- Multiple inference backends: Gemini (primary), pyannote+Whisper (local), Whisper-only (Ollama/LM Studio)
- Speaker voiceprint enrollment per podcast
- Machine-parseable progress output for scripting
- Markdown output with timestamps

## Installation

Gemini-only (lean):

```sh
uv tool install whotalksitron
```

With local backends (pyannote, Whisper):

```sh
uv tool install whotalksitron --with local
```

## Usage

```sh
# Transcribe an episode
whotalksitron transcribe episode.mp3 --podcast my-show

# Enroll a speaker
whotalksitron enroll --name matt --podcast my-show --sample voice-sample.mp3

# List enrolled speakers
whotalksitron list-speakers --podcast my-show
```

## Configuration

```sh
whotalksitron config --init    # Create default config
whotalksitron config --show    # Show resolved config
```

Config file: `~/.config/whotalksitron/config.toml`

## Development

Requires: Python 3.11+, [uv](https://docs.astral.sh/uv/), [just](https://just.systems/)

```sh
git clone <repo-url>
cd whotalksitron
uv sync --all-extras --group dev
just test
just lint
just ensureci-sandbox
```

## License

Apache-2.0
```

- [ ] **Step 9: Initialize the project and run tests**

Run: `uv sync --group dev`
Expected: dependencies installed, virtualenv created

Run: `just test`
Expected: 2 tests pass (test_cli_help, test_cli_version)

Run: `just lint`
Expected: no lint errors

Run: `just fmt`
Expected: no formatting changes (or auto-fixes applied)

- [ ] **Step 10: Verify ensureci-sandbox**

Run: `just ensureci-sandbox`
Expected: all sandbox-safe CI checks pass (mdlint, lint, fmtcheck, secaudit, typecheck, testcover)

If any check fails, fix the issue before committing.

- [ ] **Step 11: Commit** `[COMMIT]`

```bash
git add pyproject.toml src/ tests/ justfile README.md .forgejo/workflows/ci.yml lefthook.yml
git commit -m "Set up Python project with uv, ruff, pytest, and CI

Customize repo template for whotalksitron: pyproject.toml with
click/genai/httpx/numpy deps, justfile with Python-specific CI
recipes, Forgejo Actions workflow with uv, and smoke tests for
the CLI entry point."
```
