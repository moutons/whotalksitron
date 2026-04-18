# Backend Abstraction

## Protocol

All backends implement a shared protocol:

```python
class TranscriptSegment:
    start: float        # seconds
    end: float
    text: str
    speaker: str | None  # None = unknown speaker

class TranscriptResult:
    segments: list[TranscriptSegment]
    metadata: dict  # backend-specific (model used, token count, etc.)

class Backend(Protocol):
    name: str

    def transcribe(self, audio_path: Path, *,
                   speakers: SpeakerPool | None,
                   progress: ProgressCallback | None) -> TranscriptResult: ...

    def supports_diarization(self) -> bool: ...

    def is_available(self) -> bool: ...
```

Each backend receives the `SpeakerPool` and uses it however fits its approach. The protocol does not dictate how diarization or voiceprint matching happen internally.

## Auto-Selection Logic

When `--backend` is not specified:

1. Try Gemini: available if `GEMINI_API_KEY` is set or ADC is configured.
2. Try pyannote+Whisper: available if `torch` and `pyannote.audio` are importable.
3. Try Whisper-only: available if the configured endpoint (Ollama/LM Studio) responds.
4. Error with actionable message listing what each backend needs.

If `--backend` is specified and that backend is unavailable, error immediately with the specific reason.

## Per-Backend Behavior

### Gemini

- Sends audio to the Gemini API in a single call.
- Includes enrolled voice samples (raw audio) as prompt context for speaker identification.
- Returns speaker-attributed segments directly.
- Handles chunking for files exceeding the Gemini API inline data limit (20MB). Files above this threshold are uploaded via the File API before transcription.
- Authentication: API key (`GEMINI_API_KEY` env var or config) or Google Cloud ADC.

### pyannote+Whisper

- Two-stage local pipeline.
- Stage 1: Whisper transcribes audio to timestamped text segments.
- Stage 2: pyannote diarizes audio into speaker-labeled time regions.
- Merge: align Whisper segments with pyannote speaker regions by timestamp overlap.
- Voiceprint matching: compare each diarized speaker's embedding against enrolled embeddings using cosine similarity. Match if similarity exceeds threshold (default: 0.7, configurable).
- Device selection: `auto` detects MPS (Apple Silicon) or CUDA, falls back to CPU.

### Whisper-only (Ollama / LM Studio)

- Sends audio to a local OpenAI-compatible endpoint via `httpx` (not the `openai-whisper` Python library).
- Targets the `/v1/audio/transcriptions` endpoint exposed by Ollama and LM Studio.
- Returns timestamped text without speaker attribution.
- All segments have `speaker = None`.
- No diarization, no voiceprint matching.
- The `extract-samples` command is unavailable with this backend.
