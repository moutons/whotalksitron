# Contributing

## Development Methodology

This project uses **spec-driven development** powered by
[obra/superpowers](https://github.com/obra/superpowers). Every change follows
the same sequence:

1. **Spec first.** Describe what you want to build or change in
   `docs/superpowers/specs/`. No implementation without an approved spec.
2. **Plan second.** Write an implementation plan in `docs/superpowers/plans/`.
   Plans are written before code and executed task-by-task.
3. **Code third.** Follow the plan. Commit after each task.

The full agent workflow is in `.agents/AGENTS.md`.

## Commit Conventions

All commits must follow
[Conventional Commits](https://www.conventionalcommits.org/). A `commit-msg`
hook enforces this automatically.

Format: `<type>(<optional scope>): <description>`

Types: `feat`, `fix`, `perf`, `refactor`, `docs`, `style`, `test`, `build`,
`ci`, `chore`.

Breaking changes: add `!` after the type (e.g., `feat!: remove legacy API`) or
include `BREAKING CHANGE:` in the commit body.

Versioning is automated via
[python-semantic-release](https://python-semantic-release.readthedocs.io/).
`feat` triggers a minor bump, `fix`/`perf` trigger a patch bump, and breaking
changes trigger a major bump.

## Tooling

All tasks go through the justfile. Run `just` to see available recipes.

Key recipes:

- `just test` -- run tests
- `just lint` -- run linters
- `just fmt` -- auto-format
- `just secaudit` -- secret scanning (gitleaks)
- `just ensureci-sandbox` -- sandbox-safe CI (no network-dependent checks)
- `just ensureci` -- full CI simulation

## CI Requirements

All CI checks must pass before merge. The pre-push hook runs
`just ensureci-sandbox` automatically. CI runs on Python 3.11 through 3.14.

Checks include: ruff lint/format, ty type checking, pytest with coverage,
pip-audit vulnerability scanning, and markdown linting.

## Issues and Pull Requests

Use the issue templates to report bugs or request features. Pull requests
should reference the spec or issue they address.

## Architecture Decisions

Record non-obvious decisions as ADRs in `docs/decisions/`. Format:
`NNNN-title.md` with sections: Status, Context, Decision, Consequences.
