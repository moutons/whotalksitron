# TODO

Future improvements and post-review findings.

## Warnings

### Performance: O(N*M) speaker matching

`src/whotalksitron/speakers/matching.py` — `match_speakers()` iterates all detected speakers against all enrolled speakers. Fine for typical podcast sizes (5-10 speakers), but would need indexing for larger pools.

### Performance: O(N*M) diarization merge

`src/whotalksitron/backends/pyannote.py` — `_find_majority_speaker()` scans all diarization regions for every transcript segment. For typical podcast episodes (hundreds of segments, hundreds of regions) this is fine. For very long recordings or fine-grained diarization, it could become a bottleneck. Optimization: sort diarization regions by start time and use `bisect` to find the relevant window, reducing to O(S log D).

### Gemini: last segment end-time heuristic

`src/whotalksitron/backends/gemini.py:188-193` — Last segment gets a hardcoded `+30.0` seconds for its end time since Gemini only provides start timestamps. Consider using audio file duration instead.

### TOCTOU in audio validation

`src/whotalksitron/pipeline.py:validate_audio()` — File existence/size checks happen before transcription. The file could change between validation and use. Low risk for CLI usage but worth noting.

### numpy as core dependency

`src/whotalksitron/speakers/matching.py` — numpy is imported unconditionally but is only needed for voiceprint matching. Could be lazy-imported to keep the base install lighter.

### Config: tomli_w unconditional import

`src/whotalksitron/config.py:8` — `import tomli_w` at module level but only used in `write_default()`. Could lazy-import to avoid requiring the package for read-only config usage.

## Speaker System

- **ONNX embedding fallback**: `_OnnxEmbedder` in `src/whotalksitron/speakers/embeddings.py` is currently a stub that raises `NotImplementedError`. Implement using `speechbrain/spkrec-ecapa-voxceleb` exported to ONNX (~80MB download on first use) so that voiceprint enrollment works without the full pyannote/torch stack installed.

## Nits

### cli.py: `_coerce_value` branches untested

`src/whotalksitron/cli.py:368-379` — The bool/int/float coercion function has no direct unit tests. Currently exercised only through `config set` integration.

### Test coverage gaps

- No tests for `retry_with_backoff` backoff timing or exception re-raising
- No tests for `_parse_timestamp` with invalid input (now that validation was added)
- No edge-case tests for `_safe_dirname` with path traversal attempts

### gemini.py: response parsing regex

`src/whotalksitron/backends/gemini.py:150-153` — The speaker name regex only matches `[A-Z]` initial caps. Won't match lowercase or non-ASCII speaker names from Gemini responses.

### Naming inconsistency: `_GENERIC_PATTERN` vs `unmatched_speakers`

`src/whotalksitron/speakers/matching.py:13` and `src/whotalksitron/models.py:44` — Both detect "generic" speaker labels but use different names for the concept. Consider unifying terminology.
