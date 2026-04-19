# Backends

whotalksitron supports three transcription backends. Auto-selection picks the first available based on configured credentials.

## Gemini (recommended)

Uses Google's Gemini models via Vertex AI or AI Studio. Handles any audio format, produces diarized output in a single API call.

**Requirements:** API credentials. See [gcloud.md](gcloud.md) for Vertex AI setup.

**Auto-selected when:** `gemini.api_key` or `gemini.use_adc` is configured.

**Formats:** mp3, wav, flac, m4a, webm, ogg. Other formats are converted to WAV via ffmpeg before upload.

**Large files (Vertex AI):** Files over 20 MB are staged to a GCS bucket before being sent to the model. Set `GOOGLE_CLOUD_STORAGE_BUCKET` or `gemini.gcs_bucket`. See [gcloud.md](gcloud.md).

**Models:** Any Gemini model that supports audio input. Default: `gemini-2.5-flash`.

```sh
whotalksitron transcribe episode.mp3 --backend gemini --model gemini-2.5-flash
```

## pyannote (local)

Runs [pyannote.audio](https://github.com/pyannote/pyannote-audio) for speaker diarization and [faster-whisper](https://github.com/SYSTRAN/faster-whisper) for transcription. Fully local, no external API calls.

**Requirements:** `uv tool install whotalksitron --with local`. GPU or Apple Silicon strongly recommended — CPU inference is slow.

**Auto-selected when:** pyannote, torch, and faster-whisper are importable (i.e. the `local` extra is installed).

**Formats:** WAV only. Other formats are converted automatically if ffmpeg is installed.

**Models:** Configured via `pyannote.whisper_model` (default: `large-v3`) and `pyannote.diarization_model`.

**Device:** Auto-detected (`mps` on Apple Silicon, `cuda` if available, otherwise `cpu`). Override with `pyannote.device`.

```sh
whotalksitron transcribe episode.mp3 --backend pyannote
```

## Whisper (Ollama / LM Studio)

Sends audio to a local OpenAI-compatible Whisper endpoint. Transcription only — no speaker diarization.

**Requirements:** Ollama or LM Studio running locally with a Whisper model loaded.

**Auto-selected when:** The configured endpoint is reachable (not currently checked at startup — falls through to this backend if neither Gemini nor pyannote is available).

**Formats:** Depends on the server.

**Config:**

```toml
[whisper]
endpoint = "http://localhost:1234/v1"
model = "whisper-large-v3"
```

```sh
whotalksitron transcribe episode.mp3 --backend whisper
```

## Auto-selection order

1. `gemini` — if `gemini.api_key` or `gemini.use_adc` is set
2. `pyannote` — if the local extra is installed
3. `whisper` — always attempted last

Override with `--backend` or `defaults.backend` in config.

## ffmpeg

ffmpeg is used to convert non-native audio formats before sending to pyannote or Gemini.

Install: `brew install ffmpeg` (macOS) or `apt install ffmpeg` (Debian/Ubuntu).

If ffmpeg is not installed and conversion is needed, the pipeline raises an error with install instructions.
