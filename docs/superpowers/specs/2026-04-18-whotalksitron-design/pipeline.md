# Transcription Pipeline

## Stages

Every transcription follows six stages:

```
Input audio
  → [1] Validate    (format, duration, file size)
  → [2] Pre-process (convert to WAV/PCM if needed, via ffmpeg)
  → [3] Transcribe  (backend produces TranscriptResult)
  → [4] Voiceprint  (relabel segments where confidence > threshold)
  → [5] Format      (render to markdown)
  → [6] Write       (save output file)
```

Progress is reported at each stage boundary via stderr JSON lines when `--progress` is enabled.

## Pre-processing

The tool requires `ffmpeg` on PATH. If missing, error with platform-specific install instructions rather than failing cryptically.

- Local backends (pyannote, whisper): convert to 16kHz mono WAV.
- Gemini: skip conversion when the input is MP3, WAV, or FLAC (natively supported). Convert other formats.

## Voiceprint Matching (Stage 4)

- **Gemini:** mostly a no-op. Gemini received voice samples in the prompt and labeled segments directly. If Gemini returned generic labels despite having samples, fall back to embedding-based matching.
- **pyannote:** compare each diarized speaker's embedding against enrolled embeddings. Match if cosine similarity exceeds the threshold.
- **Whisper-only:** skip. No speaker information to match against.

## Output Format

Inline speaker labels with timestamps. Dense, readable as markdown:

```markdown
# Transcript: episode-123.mp3

<!-- whotalksitron | 2026-04-18T14:30:00Z | gemini-2.5-flash | 01:23:45 | podcast:atp -->

**[00:00:00] Matt:** Welcome back to the show. Today we're talking about the new release and what it means for the ecosystem.

**[00:00:15] Speaker 02:** Yeah, I've been looking forward to this one. There's a lot to unpack.

**[00:00:22] Matt:** So let's dive right in. The first thing I wanted to cover is the breaking change in the API.
```

The HTML comment metadata line is pipe-delimited for machine parsing. Fields: tool name, ISO 8601 timestamp, backend model, duration, podcast scope.

Mixed speaker labels are expected. Some segments labeled with enrolled names ("Matt:"), others with zero-padded generic identifiers ("Speaker 02:") in the same transcript. Padding auto-increments when speaker count exceeds capacity (minimum 2 digits).
