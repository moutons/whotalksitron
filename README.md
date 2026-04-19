# whotalksitron

Audio transcription CLI with speaker identification. Accepts audio files, produces markdown transcripts with speaker-attributed segments and timestamps.

## Features

- Multiple inference backends: Gemini via Vertex AI (primary), pyannote+Whisper (local), Whisper-only (Ollama/LM Studio)
- Speaker voiceprint enrollment per podcast — enroll known voices, re-identify them automatically in future episodes
- Markdown output with timestamps and speaker labels
- Machine-parseable progress output for scripting

## Installation

Gemini-only (lean, no GPU required):

```sh
uv tool install whotalksitron
```

With local backends (pyannote+faster-whisper, requires GPU or Apple Silicon):

```sh
uv tool install whotalksitron --with local
```

## Quickstart

```sh
# Transcribe with Gemini (requires API credentials — see docs/gcloud.md)
whotalksitron transcribe episode.mp3 --backend gemini --podcast my-show

# Transcribe with a local backend
whotalksitron transcribe episode.mp3 --backend pyannote

# Enroll a known speaker
whotalksitron enroll --name alice --podcast my-show --sample alice-sample.wav

# Transcribe with speaker identification
whotalksitron transcribe episode.mp3 --backend gemini --podcast my-show
```

Output is written alongside the audio file as `episode.md` by default.

## Commands

### `transcribe`

```
whotalksitron transcribe AUDIO_FILE [OPTIONS]
```

| Option | Description |
|---|---|
| `--backend` | `gemini`, `pyannote`, or `whisper`. Defaults to auto-select. |
| `--podcast NAME` | Load enrolled speakers for this podcast and run voiceprint matching. |
| `--output PATH` | Output path. Defaults to audio file with `.md` extension. |
| `--model NAME` | Override the model for the selected backend. |
| `--identify-speakers` | Force speaker identification even without enrolled voices. |

### `enroll`

Add a voice sample for a speaker. Run multiple times to add more samples.

```
whotalksitron enroll --name NAME --podcast PODCAST --sample AUDIO_FILE
```

| Option | Description |
|---|---|
| `--name` | Speaker name as it will appear in transcripts. |
| `--podcast` | Podcast identifier (used to scope speakers per show). |
| `--sample` | Audio file containing only this speaker's voice. |
| `--rebuild` | Recompute embeddings from existing samples. |

### `extract-samples`

Transcribe an episode and extract short audio clips per speaker — useful for building an enrollment library without manually slicing audio.

```
whotalksitron extract-samples AUDIO_FILE [--podcast PODCAST] [--output DIR]
```

Prints enrollment commands for any unrecognised speakers at the end.

### `import-speaker`

Copy an enrolled speaker from one podcast to another without re-enrolling.

```
whotalksitron import-speaker --name NAME --from SOURCE_PODCAST --to TARGET_PODCAST
```

### `list-speakers`

```
whotalksitron list-speakers [--podcast PODCAST]
```

### `config`

```
whotalksitron config --init           # Write default config to ~/.config/whotalksitron/config.toml
whotalksitron config --show           # Print resolved config (with secrets masked)
whotalksitron config --set key=value  # Update a single key in the config file
```

## Global flags

These apply to all commands:

| Flag | Description |
|---|---|
| `--log-level` | `debug`, `info`, `warn`, `error` |
| `--log-format` | `text` (default) or `json` |
| `--progress` | Emit structured progress lines to stderr |
| `--quiet` / `-q` | Suppress non-error output |

## Configuration

Config file lives at `~/.config/whotalksitron/config.toml`. Generate a template with `whotalksitron config --init`.

Configuration is resolved in this order (later overrides earlier):

1. Config file
2. macOS Keychain (for Gemini API key)
3. 1Password CLI (for Gemini API key, if `gemini.op_reference` is set)
4. Environment variables
5. CLI flags

### Environment variables

| Variable | Config key | Description |
|---|---|---|
| `GOOGLE_CLOUD_API_KEY` | `gemini.api_key` | Gemini/Vertex AI API key |
| `GOOGLE_CLOUD_PROJECT` | `gemini.project` | GCP project ID |
| `GOOGLE_CLOUD_LOCATION` | `gemini.location` | GCP region |
| `GOOGLE_GENAI_USE_VERTEXAI` | `gemini.use_adc` | Set to `1` to use Vertex AI instead of AI Studio |
| `GOOGLE_CLOUD_STORAGE_BUCKET` | `gemini.gcs_bucket` | GCS bucket for staging large audio files (Vertex AI only) |
| `GEMINI_API_KEY` | `gemini.api_key` | Alternative to `GOOGLE_CLOUD_API_KEY` |
| `WHOTALKSITRON_BACKEND` | `defaults.backend` | Default backend |
| `WHOTALKSITRON_LOG_LEVEL` | `defaults.log_level` | Default log level |
| `WHOTALKSITRON_CONFIG` | — | Override config file path |
| `WHOTALKSITRON_SPEAKERS_DIR` | — | Override speakers directory |

### Config file reference

```toml
[defaults]
backend = "auto"        # auto, gemini, pyannote, whisper
log_level = "info"
progress = false

[gemini]
api_key = ""
use_adc = false         # true = Vertex AI via ADC
project = ""            # GCP project (Vertex AI)
location = ""           # GCP region (Vertex AI)
gcs_bucket = ""         # GCS bucket for large files (Vertex AI)
model = "gemini-2.5-flash"

[pyannote]
whisper_model = "large-v3"
diarization_model = "pyannote/speaker-diarization-3.1"
device = "auto"         # auto, cpu, cuda, mps

[whisper]
endpoint = "http://localhost:1234/v1"
model = "whisper-large-v3"

[speakers]
match_threshold = 0.7   # cosine similarity threshold for voiceprint matching

[output]
timestamp_format = "HH:MM:SS"
```

## Backends

| Backend | Requires | Diarization | Notes |
|---|---|---|---|
| `gemini` | Gemini or Vertex AI credentials | Yes | Best quality, handles any format |
| `pyannote` | `--with local`, torch, GPU recommended | Yes | Fully local, slower |
| `whisper` | Ollama or LM Studio running locally | No | Transcription only |

Backend is selected automatically in the order above based on what credentials are available. Override with `--backend`.

## Speakers directory

Enrolled speaker data lives at `~/.config/whotalksitron/speakers/`. Each speaker is stored per podcast:

```
~/.config/whotalksitron/speakers/
  my-show/
    alice/
      sample-001.wav
      embedding.npy
      meta.json
```

## Development

Requires: Python 3.11+, [uv](https://docs.astral.sh/uv/), [just](https://just.systems/)

```sh
git clone <repo-url>
cd whotalksitron
uv sync --all-extras --group dev
just test          # run tests
just lint          # lint
just ensureci-sandbox  # full local CI (no network)
```

See [docs/gcloud.md](docs/gcloud.md) for Vertex AI setup.

## License

Apache-2.0
