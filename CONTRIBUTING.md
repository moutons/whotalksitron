# Contributing

This project uses spec-driven development. Read `.agents/AGENTS.md` for the full workflow.

## Process

1. **Spec first.** Create a spec in `docs/superpowers/specs/` describing what you want to build or change.
2. **Plan second.** Write an implementation plan in `docs/superpowers/plans/`.
3. **Code third.** Follow the plan, committing after each task.

## Requirements

- All CI checks must pass before merge: `just ensureci-sandbox`
- Use the issue templates to report bugs or request features.
- Record non-obvious decisions as ADRs in `docs/decisions/`.

## Tooling

All tasks go through the justfile. Run `just` to see available recipes.
