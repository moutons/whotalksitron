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
    gitleaks git --platform gitea --platform github .

# Full CI simulation
ensureci: _ci_mdlint _ci_lint _ci_fmtcheck _ci_vulncheck _ci_secaudit _ci_typecheck _ci_testcover _ci_workflows
    @echo "All CI checks passed!"

# Sandbox-safe CI (no TLS-dependent checks)
ensureci-sandbox: _ci_mdlint _ci_lint _ci_fmtcheck _ci_secaudit _ci_typecheck _ci_testcover _ci_workflows
    @echo "All sandbox-compatible CI checks passed! (vulncheck skipped)"

# Quick validation
isgreen: fmt lint test

# Remove build artifacts
clean:
    rm -rf dist/ build/ .ruff_cache/ .pytest_cache/ htmlcov/
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    find . -name "*.pyc" -delete 2>/dev/null || true

# Install as a tool using uv
install:
    uv tool install . --force --reinstall

# --- CI sub-recipes (hidden from `just --list`) ---

_ci_mdlint:
    npx --yes markdownlint-cli2 "**/*.md" "#node_modules" "#.venv" "#.pytest_cache" "#.private-journal"

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

_ci_workflows:
    npx --yes pin-github-action .github/workflows/*.yml
    zizmor --config .github/zizmor.yml .github/workflows/

# Conventional Commits pattern
_cc_pattern := '^(feat|fix|perf|refactor|docs|style|test|build|ci|chore)(\(.+\))?(!)?: .+'

# Validate a single commit message file (used by commit-msg hook)
_ci_commitmsg msgfile:
    #!/usr/bin/env bash
    msg=$(head -1 "{{msgfile}}")
    if ! echo "$msg" | grep -qE '{{_cc_pattern}}'; then
      echo "ERROR: commit message must follow Conventional Commits"
      echo "  Format: <type>[optional scope][!]: <description>"
      echo "  Types: feat, fix, perf, refactor, docs, style, test, build, ci, chore"
      echo "  Got: $msg"
      exit 1
    fi

# Validate all commits in a range (used by pre-push hook)
_ci_commitrange range:
    #!/usr/bin/env bash
    bad=""
    for sha in $(git rev-list "{{range}}" 2>/dev/null); do
      msg=$(git log --format=%s -n 1 "$sha")
      if ! echo "$msg" | grep -qE '{{_cc_pattern}}'; then
        bad="$bad\n  $sha $msg"
      fi
    done
    if [ -n "$bad" ]; then
      echo "ERROR: non-conventional commit messages found:$bad"
      echo ""
      echo "All commits must match: <type>[scope][!]: <description>"
      exit 1
    fi

# Verify all commits in a range are signed (used by pre-push hook)
_ci_sigcheck range:
    #!/usr/bin/env bash
    unsigned=""
    for sha in $(git rev-list "{{range}}" 2>/dev/null); do
      sig=$(git log --format='%G?' -n 1 "$sha")
      if [ "$sig" = "N" ] || [ -z "$sig" ]; then
        msg=$(git log --format='%h %s' -n 1 "$sha")
        unsigned="$unsigned\n  $msg"
      fi
    done
    if [ -n "$unsigned" ]; then
      echo "ERROR: unsigned commits found:$unsigned"
      echo ""
      echo "Configure commit signing: git config commit.gpgsign true"
      exit 1
    fi
