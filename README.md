# whotalksitron

Audio transcription CLI with speaker identification. Accepts audio files, produces markdown transcripts with speaker-attributed segments and timestamps.

## Features

- Multiple inference backends: Gemini (primary), pyannote+Whisper (local), Whisper-only (Ollama/LM Studio)
- Speaker voiceprint enrollment per podcast
- Machine-parseable progress output for scripting
- Markdown output with timestamps

## Installation

Gemini-only (lean):

```sh
uv tool install whotalksitron
```

With local backends (pyannote, Whisper):

```sh
uv tool install whotalksitron --with local
```

## Usage

```sh
# Transcribe an episode
whotalksitron transcribe episode.mp3 --podcast my-show

# Enroll a speaker
whotalksitron enroll --name matt --podcast my-show --sample voice-sample.mp3

# List enrolled speakers
whotalksitron list-speakers --podcast my-show
```

## Configuration

```sh
whotalksitron config --init    # Create default config
whotalksitron config --show    # Show resolved config
```

Config file: `~/.config/whotalksitron/config.toml`

## Development

Requires: Python 3.11+, [uv](https://docs.astral.sh/uv/), [just](https://just.systems/)

```sh
git clone <repo-url>
cd whotalksitron
uv sync --all-extras --group dev
just test
just lint
just ensureci-sandbox
```

## License

Apache-2.0
