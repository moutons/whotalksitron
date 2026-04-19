from __future__ import annotations

from datetime import UTC, datetime

from whotalksitron.models import TranscriptResult, _format_timestamp


def render_transcript(
    result: TranscriptResult,
    source_file: str,
    podcast: str | None = None,
) -> str:
    lines: list[str] = []

    lines.append(f"# Transcript: {source_file}")
    lines.append("")
    lines.append(_metadata_comment(result, podcast))
    lines.append("")

    for segment in result.segments:
        ts = segment.start_timestamp
        if segment.speaker:
            lines.append(f"**[{ts}] {segment.speaker}:** {segment.text}")
        else:
            lines.append(f"**[{ts}]** {segment.text}")
        lines.append("")

    return "\n".join(lines)


def _metadata_comment(result: TranscriptResult, podcast: str | None) -> str:
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    model = result.metadata.get("model", "unknown")
    duration = _format_timestamp(result.duration)

    parts = ["whotalksitron", now, str(model), duration]
    if podcast:
        parts.append(f"podcast:{podcast}")

    return "<!-- " + " | ".join(parts) + " -->"
