# Agent Instructions

Read this file first. It contains the development methodology for this repository.
Claude-specific configuration is in `.claude/CLAUDE.md`.

## Development Methodology

This project uses spec-driven development with [obra/superpowers](https://github.com/obra/superpowers).

1. **Spec first.** Every feature, bugfix, or refactor starts with a spec in `docs/superpowers/specs/`. No implementation without an approved spec.
2. **Plan second.** Implementation plans live in `docs/superpowers/plans/`. Plans are written before code and executed task-by-task.
3. **Code third.** Follow the plan. Commit after each task.

## Agent Dispatch

Prefer the lightest-weight agent possible for any task:

- **Cheapest model** (e.g., haiku): deterministic work -- file lookups, formatting checks, simple searches, running tests.
- **Mid-tier model** (e.g., sonnet): moderate complexity -- code review, standard implementations, debugging.
- **Expensive model** (e.g., opus): deep reasoning only -- architectural decisions, complex refactors, ambiguous specs.

Give agents focused, complete prompts so they can work autonomously and return exactly what you need.

## Progressive Disclosure

Load only the context you need. Do not read the entire codebase to fix a typo.

Deterministic checks are enforced via lefthook git hooks:

- **Pre-commit** (lightweight): markdown linting, format checking. These run fast and should never be skipped. Commit freely -- pre-commit won't slow you down.
- **Pre-push** (full): `just ensureci-sandbox` runs all sandbox-safe CI checks (lint, format, security, tests, build). This is the gate that matters. If pre-push fails, fix the issue before pushing.

Agents do not need to internalize formatting or linting rules. The hooks catch violations automatically. Focus on writing correct code; the hooks handle style.

## Justfile as Single Source of Truth

All common tasks go through `just`. Do not invoke formatters, linters, or test runners directly -- use the justfile recipes. This prevents divergence when different agents default to different tools.

Key recipes:

- `just test` -- run tests
- `just lint` -- run linters
- `just fmt` -- auto-format
- `just ensureci` -- full CI simulation
- `just ensureci-sandbox` -- sandbox-safe CI (no network-dependent checks)

## Conventional Commits

All commit messages must follow the [Conventional Commits](https://www.conventionalcommits.org/) specification. This is enforced by a `commit-msg` lefthook hook.

Format: `<type>(<optional scope>): <description>`

Allowed types:

- `feat` -- new feature (triggers minor version bump)
- `fix` -- bug fix (triggers patch version bump)
- `perf` -- performance improvement (triggers patch version bump)
- `refactor` -- code change that neither fixes a bug nor adds a feature
- `docs` -- documentation only
- `style` -- formatting, whitespace, etc.
- `test` -- adding or updating tests
- `build` -- build system or dependencies
- `ci` -- CI configuration
- `chore` -- maintenance tasks

Breaking changes: add `!` after the type/scope (e.g., `feat!: remove legacy API`) or include `BREAKING CHANGE:` in the commit body. This triggers a major version bump.

Scopes are optional but encouraged for clarity (e.g., `feat(cli):`, `fix(gemini):`).

## Architecture Decision Records

Non-obvious decisions go in `docs/decisions/` as lightweight ADRs.

Before making a choice that could go either way, check for an existing ADR. Format: `NNNN-title.md` with sections: Status, Context, Decision, Consequences.

## Emergent Decisions

When a decision arises about conventions, tooling, or patterns: **ask the user** whether it belongs in:

- **Project settings** (`.agents/AGENTS.md`, `.claude/settings.json`) -- applies to this repo only
- **User-profile settings** (`~/.claude/CLAUDE.md`, `~/.claude/settings.json`) -- applies to all repos

Do not silently commit to a convention without surfacing this choice.

## Git Worktrees

When using git worktrees for isolated work, place them in `.worktrees/` at the repository root. This directory is gitignored.

```bash
git worktree add .worktrees/<branch-name> -b <branch-name>
```

## Shell Script Portability

All shell scripts must be compatible with macOS default bash 3.2 (GPLv2). Do not use bash 4+ features:

- No `${VAR^}` / `${VAR,,}` (case modification) -- use `awk` or `tr` instead
- No `declare -A` (associative arrays) -- use indexed arrays
- No `|&` (pipe stderr) -- use `2>&1 |`
- When in doubt, prefer POSIX sh constructs over bash-specific features

## Version Pinning

Preferred pinning order (most preferred first):

1. Commit SHA
2. Full version number (e.g., `v1.2.3`)
3. Unversioned pin (e.g., `v1`)
4. No pinning -- **never use this**

Apply to: CI action references, dependency locks, tool versions. Never use `@latest` tags.
