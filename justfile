# Default recipe: show available recipes
default:
    @just --list

# Run all tests
test: _ci_testcover

# Run linter(s)
lint: _ci_lint

# Auto-format code
fmt:
    @echo "fmt: configure per language"
    @echo "  Go:     golangci-lint run --fix"
    @echo "  JS/TS:  bun prettier --write ."
    @echo "  Python: ruff format ."
    @echo "  Ruby:   rvx rubocop -a"

# Security audit (gitleaks + language-specific static analysis)
secaudit: _ci_secaudit
    gitleaks git --platform gitea .

# Full CI simulation
ensureci: _ci_mdlint _ci_lint _ci_fmtcheck _ci_vulncheck _ci_secaudit _ci_typecheck _ci_testcover _ci_build
    @echo "All CI checks passed!"

# Sandbox-safe CI (no TLS-dependent checks)
ensureci-sandbox: _ci_mdlint _ci_lint _ci_fmtcheck _ci_secaudit _ci_typecheck _ci_testcover _ci_build
    @echo "All sandbox-compatible CI checks passed! (vulncheck skipped)"

# Quick validation
isgreen: fmt lint test

# Remove build artifacts
clean:
    @echo "clean: configure per language"
    @echo "  Go:     go clean"
    @echo "  JS/TS:  rm -rf dist node_modules"
    @echo "  Python: rm -rf __pycache__ .ruff_cache .pytest_cache"
    @echo "  Ruby:   rm -rf tmp vendor"

# --- CI sub-recipes (hidden from `just --list`) ---

_ci_mdlint:
    npx --yes markdownlint-cli2 "**/*.md" "#node_modules"

_ci_lint:
    @echo "_ci_lint: configure per language"
    @echo "  Go:     golangci-lint run"
    @echo "  JS/TS:  bun lint"
    @echo "  Python: ruff check ."
    @echo "  Ruby:   rvx rubocop"

_ci_fmtcheck:
    @echo "_ci_fmtcheck: configure per language"
    @echo "  Go:     golangci-lint run --disable-all -E gofmt"
    @echo "  JS/TS:  bun prettier --check ."
    @echo "  Python: ruff format --check ."
    @echo "  Ruby:   rvx rubocop -f"

_ci_vulncheck:
    @echo "_ci_vulncheck: configure per language (requires network)"
    @echo "  Go:     govulncheck ./..."
    @echo "  JS/TS:  bun audit"
    @echo "  Python: uv pip audit"
    @echo "  Ruby:   rvx bundler-audit"

_ci_secaudit:
    @echo "_ci_secaudit: configure per language"
    @echo "  Go:     gosec ./..."
    @echo "  JS/TS:  (n/a)"
    @echo "  Python: ruff check --select S ."
    @echo "  Ruby:   rvx brakeman"

_ci_typecheck:
    @echo "_ci_typecheck: configure per language"
    @echo "  Go:     (compiled)"
    @echo "  JS/TS:  bun tsc --noEmit"
    @echo "  Python: ty check"
    @echo "  Ruby:   rvx sorbet"

_ci_testcover:
    @echo "_ci_testcover: configure per language"
    @echo "  Go:     go test -race -cover ./..."
    @echo "  JS/TS:  bun test --coverage"
    @echo "  Python: uv run pytest --cov"
    @echo "  Ruby:   rvx rspec"

_ci_build:
    @echo "_ci_build: configure per language"
    @echo "  Go:     go build ./..."
    @echo "  JS/TS:  bun build"
    @echo "  Python: (n/a)"
    @echo "  Ruby:   (n/a)"
