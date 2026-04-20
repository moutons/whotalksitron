# Speaker Enrollment & Voiceprint Storage

## Data Layout

```
~/.config/whotalksitron/
├── config.toml
├── staging/              # temp samples from --identify-speakers (non-TTY)
│   └── <episode-stem>/
│       └── speaker-N/
└── speakers/
    └── <podcast>/
        └── <speaker>/
            ├── meta.toml
            ├── samples/
            │   ├── sample-a1b2c3d4e5f6.mp3
            │   └── sample-f6e5d4c3b2a1.wav
            └── embeddings/
                └── embedding.npy
```

`meta.toml` contains speaker name, enrollment date, and sample count. Updated on each enrollment.

## Enrollment Flow

1. User runs `whotalksitron enroll --name matt --podcast atp --sample clip.mp3`.
2. Validate audio: readable, warn if <5s or >60s.
3. Copy sample to `speakers/atp/matt/samples/`.
4. Compute speaker embedding from the sample.
5. Average with any existing embeddings for this speaker. Save to `embedding.npy`.
6. Confirm: `Enrolled "matt" for podcast "atp" (3 samples, embedding updated)`.

## Embedding Model

Primary: pyannote's `wespeaker-voxceleb-resnet34` (small speaker verification model).

Fallback: `speechbrain/spkrec-ecapa-voxceleb` exported to ONNX, downloaded on first enrollment (~80MB). This allows enrollment even when only the Gemini backend is installed. Gemini receives raw audio samples (not embeddings) as prompt context, but the ONNX model enables the shared voiceprint matching layer for any future local backend use.

## Re-enrollment

`whotalksitron enroll --name matt --podcast atp --rebuild` recomputes a fresh average embedding across all stored samples. Useful when the embedding model is upgraded or when new samples change the speaker profile.

## Import

`whotalksitron import-speaker --name matt --from atp --to the-talk-show` copies the speaker directory (samples + embeddings) into the target podcast scope. No recomputation needed.

## Voiceprint Matching

Voiceprint matching is a post-processing step, not part of the backend protocol. After any backend returns a `TranscriptResult`:

1. Load enrolled speakers for the specified podcast.
2. For segments with generic labels ("Speaker N") or `None`, compare the speaker's audio against enrolled embeddings.
3. Match if cosine similarity exceeds the configured threshold (default: 0.7, exclusive — similarity must be strictly greater than threshold).
4. Replace generic labels with enrolled speaker names. Leave unmatched segments as-is.

**Speaker label format:** Generic speakers are zero-padded: `Speaker 01`, `Speaker 02`, etc. Padding width auto-increments when count exceeds capacity (e.g., >99 speakers → `Speaker 001`). Minimum padding is 2 digits.

**Exception:** The Gemini backend handles matching internally by sending voice samples as prompt context. The post-processing step still runs as a fallback if Gemini returned generic labels despite receiving samples.

## Sample Extraction Quality Heuristics

When extracting candidate samples (for `--identify-speakers` or `extract-samples`):

- Prefer segments >10 seconds of continuous speech.
- Avoid segments with crosstalk (overlapping speaker timestamps).
- Pick segments from different parts of the episode for diversity.
- Store 2-3 best candidates per speaker.
