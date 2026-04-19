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
    npx --yes markdownlint-cli2 "**/*.md" "#node_modules" "#.venv" "#.pytest_cache"

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
