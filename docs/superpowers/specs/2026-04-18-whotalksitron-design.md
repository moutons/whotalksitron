# whotalksitron Design Spec

Audio transcription CLI with speaker identification. Accepts audio files (MP3 at minimum), produces markdown transcripts with speaker-attributed segments and timestamps.

## Scope

| In scope | Out of scope |
|---|---|
| CLI tool installable via `uv tool install` | GUI or web interface |
| Gemini, pyannote+Whisper, Whisper-only backends | Real-time/streaming transcription |
| Speaker enrollment with voiceprints per podcast | Speaker enrollment from video |
| Machine-parseable progress on stderr | File splitting by time chunks |
| Markdown output with timestamps | Output formats beyond markdown |

## Sub-files

| File | Contents |
|---|---|
| [cli.md](2026-04-18-whotalksitron-design/cli.md) | Commands, global flags, progress format, speaker extraction flows |
| [backends.md](2026-04-18-whotalksitron-design/backends.md) | Backend protocol, selection logic, per-backend behavior |
| [speakers.md](2026-04-18-whotalksitron-design/speakers.md) | Enrollment, voiceprint storage, matching, import |
| [pipeline.md](2026-04-18-whotalksitron-design/pipeline.md) | Transcription stages, pre-processing, output format |
| [config.md](2026-04-18-whotalksitron-design/config.md) | Configuration file, precedence, settings |
| [packaging.md](2026-04-18-whotalksitron-design/packaging.md) | Project structure, dependencies, installation |
| [errors.md](2026-04-18-whotalksitron-design/errors.md) | Error categories, exit codes, diagnostics |

## Architecture Overview

```
CLI (click)
  │
  ├─ config.py          ← resolves flags > env > config.toml > defaults
  │
  ├─ pipeline.py        ← orchestrates the 6-stage transcription flow
  │   │
  │   ├─ backends/      ← Backend protocol + 3 implementations
  │   │   ├─ gemini     (API, diarization built-in, voiceprints via prompt context)
  │   │   ├─ pyannote   (local, Whisper transcription + pyannote diarization)
  │   │   └─ whisper    (local, Ollama/LM Studio, transcription only)
  │   │
  │   └─ speakers/      ← voiceprint matching (post-processing layer)
  │       ├─ enrollment (enroll, import, list, extract)
  │       ├─ matching   (cosine similarity against enrolled embeddings)
  │       └─ embeddings (ECAPA-TDNN via pyannote or ONNX fallback)
  │
  └─ output.py          ← markdown renderer
```

## Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Language | Python | Diarization ecosystem is overwhelmingly Python. pyannote, speaker embeddings, torch all native. |
| Backend priority | Gemini > pyannote > whisper-only | Gemini is cheapest (~$0.04/hr on Flash) and highest quality. Local is fallback. |
| Voiceprint in Gemini | Send voice samples as prompt context | Avoids a separate matching step. Gemini identifies speakers by name in one API call. |
| Voiceprint storage | Raw samples + computed embeddings | Samples kept for re-enrollment when embedding model upgrades. |
| Speaker scoping | Per-podcast with cross-podcast import | Narrows the matching pool. Same person can have different enrollment quality per show. |
| Progress reporting | JSON lines on stderr | Callers parse structured progress without interfering with stdout transcript output. |
| Packaging | Single package, optional `local` extra | `uv tool install whotalksitron` is lean. `--with local` adds pyannote/torch. |

## Quality Bar

Searchable and skimmable. Minor transcription errors are acceptable. This tool is for personal use, not publishing.

## Hardware Context

- Primary: M1 Max, 32GB RAM (sweet spot ~10B parameter models)
- Secondary: 64GB RAM, GTX 1070 Ti (8GB VRAM), running Ollama
