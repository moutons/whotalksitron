# Speaker Enrollment

whotalksitron can identify known speakers in a transcript by comparing voice embeddings. This requires enrolling voice samples for each speaker ahead of time.

## How it works

1. You enroll one or more audio clips per speaker (one speaker per file, clean speech)
2. whotalksitron computes a voiceprint embedding from each clip and averages them
3. During transcription, the backend produces per-speaker embeddings from the audio
4. Embeddings are compared with cosine similarity; segments above `match_threshold` are relabelled

Voiceprint matching runs after transcription and does not affect the transcript text — only speaker labels.

## Backends and diarization

Speaker identification requires a backend that supports diarization:

| Backend | Diarization | Voiceprint matching |
|---|---|---|
| `gemini` | Yes (built-in) | Yes |
| `pyannote` | Yes | Yes |
| `whisper` | No | No |

## Enrolling a speaker

```sh
whotalksitron enroll \
  --name "Alice" \
  --podcast my-show \
  --sample alice-voice.wav
```

Run the command multiple times with different samples to improve accuracy. Each sample is stored and the embedding is re-averaged across all samples.

Good samples are:

- 10–30 seconds of clean speech
- One speaker only, no background noise
- Recorded with the same microphone setup used in the podcast if possible

## Extracting samples from an episode

If you don't have clean reference recordings, you can pull samples directly from a transcribed episode:

```sh
whotalksitron extract-samples episode.mp3 --podcast my-show --output ./samples
```

This transcribes the episode, identifies speaker regions, and saves the highest-scoring clips per speaker to `./samples/`. At the end it prints the exact `enroll` commands to run:

```
To enroll unmatched speakers:
  whotalksitron enroll --name NAME --podcast my-show --sample samples/speaker-01/sample-001.wav
```

Replace `NAME` with the actual speaker's name.

## Listing enrolled speakers

```sh
whotalksitron list-speakers                  # all podcasts
whotalksitron list-speakers --podcast my-show  # one podcast
```

## Importing a speaker across podcasts

If a speaker appears on multiple shows, you can import their voiceprint without re-enrolling:

```sh
whotalksitron import-speaker \
  --name "Alice" \
  --from my-show \
  --to other-show
```

## Rebuilding embeddings

If you add samples manually to the speakers directory, rebuild the stored embedding:

```sh
whotalksitron enroll --name "Alice" --podcast my-show --sample any-existing.wav --rebuild
```

## Storage layout

```
~/.config/whotalksitron/speakers/
  my-show/
    alice/
      sample-001.wav   # original audio clips
      sample-002.wav
      embedding.npy    # averaged voiceprint embedding
      meta.json        # sample count and metadata
```

The directory can be changed with `WHOTALKSITRON_SPEAKERS_DIR`.

## Tuning match threshold

The default cosine similarity threshold is `0.7`. Raise it to reduce false matches; lower it if known speakers are being missed.

```sh
whotalksitron config --set speakers.match_threshold=0.75
```

Or set it per-run in a config override. Values between `0.6` and `0.85` are typical.
