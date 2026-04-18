# repo-template

Default repository template for new Forgejo projects. Optimized for AI coding agents, usable by humans.

## What's included

- **justfile** -- standard task runner recipes (`just test`, `just lint`, `just fmt`, `just secaudit`, `just ensureci`)
- **lefthook** -- pre-commit (lightweight checks), pre-push (`just ensureci-sandbox`)
- **markdownlint-cli2** -- deterministic markdown validation at commit-time and in CI
- **Forgejo Actions CI** -- runs `just ensureci` on push to main and PRs
- **Agent instructions** -- `.agents/AGENTS.md` (vendor-neutral) and `.claude/CLAUDE.md` (Claude-specific)
- **Issue templates** -- structured forms for bugs, features, refactors, and test gaps
- **PR template** -- checklist for spec, tests, and CI
- **Renovate** -- dependency pinning and automated updates

## Required environment variables

Set these in your shell profile or CI secrets:

| Variable | Purpose |
|---|---|
| `CLAUDEBOT_EMAIL` | Email address used for `GIT_AUTHOR_EMAIL` / `GIT_COMMITTER_EMAIL` when Claude Code commits on your behalf. |
| `CLAUDEBOT_FJ_TOKEN` | Forgejo API token for Claude Code to interact with the forge (PRs, issues, etc.). |

## Setup after cloning

1. Replace this README with your project description.
2. Update `CODEOWNERS` with the correct owner(s).
3. Fill in the justfile recipe stubs for your language (run `just` to see the skeleton).
4. Install lefthook: `lefthook install`
5. Ensure `CLAUDEBOT_EMAIL` and `CLAUDEBOT_FJ_TOKEN` are set in your environment.

## License

Apache-2.0
