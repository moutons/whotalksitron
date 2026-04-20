# whotalksitron Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI tool that transcribes audio files with speaker-attributed segments, supporting Gemini, pyannote+Whisper, and Whisper-only backends with per-podcast voiceprint enrollment.

**Architecture:** Six-stage pipeline (validate → preprocess → transcribe → voiceprint match → format → write) with a `Backend` protocol abstraction. Speaker enrollment stores raw samples and computed embeddings per podcast scope. Config resolves CLI flags > env vars > TOML file > defaults.

**Tech Stack:** Python 3.11+, click (CLI), google-genai (Gemini), pyannote.audio + torch (optional local), httpx (Whisper endpoint), numpy (embeddings), uv (packaging), ruff (lint/format), ty (type check), pytest (tests)

**Spec:** `docs/superpowers/specs/2026-04-18-whotalksitron-design.md`

---

## File Map

### Files to Create

```
pyproject.toml
src/whotalksitron/__init__.py
src/whotalksitron/cli.py
src/whotalksitron/config.py
src/whotalksitron/models.py
src/whotalksitron/pipeline.py
src/whotalksitron/output.py
src/whotalksitron/progress.py
src/whotalksitron/retry.py
src/whotalksitron/backends/__init__.py
src/whotalksitron/backends/gemini.py
src/whotalksitron/backends/pyannote.py
src/whotalksitron/backends/whisper.py
src/whotalksitron/speakers/__init__.py
src/whotalksitron/speakers/enrollment.py
src/whotalksitron/speakers/matching.py
src/whotalksitron/speakers/embeddings.py
src/whotalksitron/speakers/extraction.py
tests/conftest.py
tests/test_models.py
tests/test_config.py
tests/test_output.py
tests/test_progress.py
tests/test_retry.py
tests/test_pipeline.py
tests/test_cli.py
tests/test_backends/__init__.py
tests/test_backends/test_gemini.py
tests/test_backends/test_pyannote.py
tests/test_backends/test_whisper.py
tests/test_speakers/__init__.py
tests/test_speakers/test_enrollment.py
tests/test_speakers/test_matching.py
tests/test_speakers/test_embeddings.py
tests/test_speakers/test_extraction.py
```

### Files to Modify

```
justfile                    — Python-specific CI recipes
README.md                   — project description
.forgejo/workflows/ci.yml   — add uv + Python setup
lefthook.yml                — add fmtcheck for Python
.editorconfig               — already has *.py rule, no changes needed
```

## Phase Overview

| Phase | File | Tasks | Focus |
|---|---|---|---|
| 1 | [phase-1-repo-setup.md](2026-04-18-whotalksitron/phase-1-repo-setup.md) | 1 | Customize repo template for Python, set up pyproject.toml, justfile, CI |
| 2 | [phase-2-core.md](2026-04-18-whotalksitron/phase-2-core.md) | 5 | Core models, config, progress reporting, markdown output, retry helper |
| 3 | [phase-3-backends.md](2026-04-18-whotalksitron/phase-3-backends.md) | 3 | Backend protocol, Gemini backend, Whisper-only backend |
| 4 | [phase-4-speakers.md](2026-04-18-whotalksitron/phase-4-speakers.md) | 3 | Speaker enrollment, embeddings, voiceprint matching |
| 5 | [phase-5-integration.md](2026-04-18-whotalksitron/phase-5-integration.md) | 2 | Pipeline orchestration, CLI wiring |
| 6 | [phase-6-advanced.md](2026-04-18-whotalksitron/phase-6-advanced.md) | 2 | pyannote backend, speaker extraction flows |

## Commit and Review Schedule

| After | Action |
|---|---|
| Task 1 (repo setup) | `[COMMIT]` |
| Task 2 (models) | `[COMMIT]` |
| Task 3 (config) | `[COMMIT]` |
| Tasks 4-5 (progress + output) | `[COMMIT]` |
| Task 5b (retry helper) | `[COMMIT]` |
| Phase 2 complete | `[REVIEW:light]` — verify core foundation |
| Task 6 (backend protocol) | `[COMMIT]` |
| Task 7 (Gemini backend) | `[COMMIT]` `[REVIEW:normal]` — first working backend |
| Task 8 (Whisper backend) | `[COMMIT]` |
| Phase 3 complete | Push, `[REVIEW:light]` |
| Task 9 (enrollment) | `[COMMIT]` |
| Task 10 (embeddings) | `[COMMIT]` |
| Task 11 (matching) | `[COMMIT]` |
| Phase 4 complete | `[REVIEW:normal]` — speaker system is security-adjacent (file storage) |
| Task 12 (pipeline) | `[COMMIT]` |
| Task 13 (CLI) | `[COMMIT]` |
| Phase 5 complete | Push, `[REVIEW:full]` — end-to-end integration |
| Task 14 (pyannote) | `[COMMIT]` |
| Task 15 (extraction) | `[COMMIT]` |
| Phase 6 complete | Push, `[REVIEW:full]` — final review before merge |
