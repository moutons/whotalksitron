# CLI Surface

## Commands

### `whotalksitron transcribe <audio-file> [options]`

Main command. Accepts an audio file, produces a markdown transcript.

Flags:

- `--backend gemini|pyannote|whisper` -- override auto-selection
- `--podcast <name>` -- match speakers against this podcast's enrolled pool
- `--output <path>` -- output file path (default: `<input-stem>.md` in current directory)
- `--model <model-name>` -- override the default model for the chosen backend
- `--identify-speakers` -- after transcription, interactively identify unmatched speakers (see [Speaker Extraction Flows](#speaker-extraction-flows))

### `whotalksitron enroll --name <name> --podcast <podcast> --sample <audio-file>`

Enroll a speaker voice sample. Run multiple times to add more samples for the same speaker. Accepts `--rebuild` to recompute embeddings from all stored samples.

### `whotalksitron import-speaker --name <name> --from <podcast> --to <podcast>`

Copy a speaker's enrollment (samples + embeddings) from one podcast scope to another.

### `whotalksitron extract-samples <audio-file> [options]`

Run diarization on an audio file and extract speaker samples without full transcription. Requires a backend that supports diarization (Gemini or pyannote).

Flags:

- `--podcast <name>` -- match against enrolled speakers to identify who's already known
- `--output <dir>` -- output directory for extracted samples (default: `./samples/`)

### `whotalksitron list-speakers [--podcast <podcast>]`

Show enrolled speakers, optionally filtered by podcast scope.

### `whotalksitron config [--show | --set key=value | --init]`

Manage settings in `~/.config/whotalksitron/config.toml`.

- `--show` -- print resolved config (all sources merged, secrets masked)
- `--set gemini.model=gemini-2.5-pro` -- update a config value
- `--init` -- create a default config file with comments

## Global Flags

Available on all commands:

- `--log-level debug|info|warn|error` (default: `info`)
- `--log-format text|json` (default: `text`; `json` for structured log ingestion)
- `--progress` -- emit machine-parseable progress lines to stderr
- `--quiet` / `-q` -- suppress non-error output; still emits `--progress` if requested

## Progress Format

JSON lines on stderr, one per stage transition:

```json
{"stage": "validate", "percent": 100, "detail": "ep42.mp3, 01:23:45, 98MB"}
{"stage": "preprocess", "percent": 100, "detail": "skipped, native format"}
{"stage": "transcribe", "percent": 45, "detail": "processing chunk 3/7"}
{"stage": "diarize", "percent": 80, "detail": "matching voiceprints"}
```

Human-readable output goes to stdout. Progress goes to stderr. No mixing.

## Speaker Extraction Flows

### `--identify-speakers` (interactive)

After transcription, if unmatched speakers exist:

**User experience (TTY):**

```
Transcript complete. 2 unmatched speakers detected.

--- Speaker 3: 47 segments, 12:34 total speaking time ---
Playing sample (15s from 00:14:22)...
  [audio plays via system player]
Identify this speaker (name, or Enter to skip, 'r' to replay, 'n' for next sample): marco

Enrolled "marco" for podcast "atp" (3 samples extracted, embedding computed).
Updating transcript with new labels... done.

--- Speaker 4: 12 segments, 3:45 total speaking time ---
Playing sample (11s from 00:45:03)...
  [audio plays via system player]
Identify this speaker (name, or Enter to skip, 'r' to replay, 'n' for next sample):

Skipped. Speaker 4 remains unlabeled.

Wrote ep42.md (2 speakers identified, 1 unmatched)
```

**Non-TTY fallback:**

When stdin is not a TTY, skip interactive prompts. Extract samples to a staging directory and log the path:

```
Not a TTY. Extracted samples for 2 unmatched speakers to:
  ~/.config/whotalksitron/staging/ep42/speaker-3/
  ~/.config/whotalksitron/staging/ep42/speaker-4/
Run `whotalksitron enroll` with these samples to identify them.
```

**Behind the scenes:**

1. Normal 6-stage pipeline runs.
2. Check TranscriptResult for generic-labeled segments ("Speaker N").
3. For each unmatched speaker, collect all segments by timestamp.
4. Score segments by quality: duration >10s preferred, no overlap with other speakers, spread across the episode.
5. Select top 3 candidate segments. Extract audio clips via ffmpeg.
6. If TTY: play clips, prompt for name, enroll if named, re-run voiceprint matching (stage 4 only), re-render output.
7. If not TTY: save clips to staging directory, log paths.

### `extract-samples` (non-interactive)

**User experience:**

```
$ whotalksitron extract-samples ep42.mp3 --podcast atp

Extracted samples to ./samples/:
  speaker-1/  3 clips  (matched: matt)
  speaker-2/  3 clips  (matched: casey)
  speaker-3/  3 clips  (unmatched, 12:34 speaking time)
  speaker-4/  3 clips  (unmatched, 3:45 speaking time)

To enroll unmatched speakers:
  whotalksitron enroll --name NAME --podcast atp --sample ./samples/speaker-3/sample-001.wav
```

**Behind the scenes:**

1. Validate and pre-process input audio.
2. Run diarization only (pyannote skips Whisper; Gemini does full transcribe since diarization comes free). Whisper-only backend errors with an actionable message.
3. Voiceprint match against enrolled speakers for this podcast.
4. For each speaker (matched and unmatched), score and select top 3 segments, extract via ffmpeg.
5. Save to `--output` directory. Print summary with enrollment commands for unmatched speakers.
