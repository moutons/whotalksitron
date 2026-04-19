# Post-Implementation TODO

Remaining findings from the adversarial review (2026-04-18). Items are grouped by priority.

## Warnings

### Performance: O(N*M) speaker matching

`src/whotalksitron/speakers/matching.py` — `match_speakers()` iterates all detected speakers against all enrolled speakers. Fine for typical podcast sizes (5-10 speakers), but would need indexing for larger pools.

### Performance: O(N*M) diarization merge

`src/whotalksitron/backends/pyannote.py` — `_find_majority_speaker()` scans all diarization regions for every transcript segment. Same concern as above: fine for typical files, problematic for very long recordings.

### Gemini: last segment end-time heuristic

`src/whotalksitron/backends/gemini.py:188-193` — Last segment gets a hardcoded `+30.0` seconds for its end time since Gemini only provides start timestamps. Consider using audio file duration instead.

### TOCTOU in audio validation

`src/whotalksitron/pipeline.py:validate_audio()` — File existence/size checks happen before transcription. The file could change between validation and use. Low risk for CLI usage but worth noting.

### numpy as core dependency

`src/whotalksitron/speakers/matching.py` — numpy is imported unconditionally but is only needed for voiceprint matching. Could be lazy-imported to keep the base install lighter.

### Config: tomli_w unconditional import

`src/whotalksitron/config.py:8` — `import tomli_w` at module level but only used in `write_default()`. Could lazy-import to avoid requiring the package for read-only config usage.

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
