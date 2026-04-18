# Configuration

## Config File

Location: `~/.config/whotalksitron/config.toml`

```toml
[defaults]
backend = "auto"            # auto | gemini | pyannote | whisper
log_level = "info"
progress = false

[gemini]
# API key (also checks GEMINI_API_KEY env var)
api_key = ""
# Use Application Default Credentials instead of API key
use_adc = false
model = "gemini-2.5-flash"

[pyannote]
whisper_model = "large-v3"  # or "medium" for faster/less RAM
diarization_model = "pyannote/speaker-diarization-3.1"
device = "auto"             # auto | cpu | cuda | mps

[whisper]
# LM Studio or Ollama endpoint
endpoint = "http://localhost:1234/v1"
model = "whisper-large-v3"

[speakers]
match_threshold = 0.7       # cosine similarity threshold for voiceprint matching

[output]
timestamp_format = "HH:MM:SS"
```

## Precedence

Highest to lowest:

1. **CLI flags** (`--backend`, `--model`, `--log-level`, etc.)
2. **Environment variables** (`GEMINI_API_KEY`, `WHOTALKSITRON_BACKEND`, etc.)
3. **Config file** (`~/.config/whotalksitron/config.toml`)
4. **Built-in defaults**

## Environment Variables

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | Gemini API key (alternative to config file) |
| `WHOTALKSITRON_BACKEND` | Override default backend |
| `WHOTALKSITRON_LOG_LEVEL` | Override default log level |

## `whotalksitron config` Subcommands

- `config --show` prints the fully resolved config with all sources merged. Secrets are masked (`gemi...k3yR`).
- `config --set gemini.model=gemini-2.5-pro` updates a single value in the config file.
- `config --init` creates a default config file with comments explaining each option. Errors if the file already exists (use `--set` to modify).
