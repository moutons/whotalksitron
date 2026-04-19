from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str
    speaker: str | None = None

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def start_timestamp(self) -> str:
        return _format_timestamp(self.start)

    @property
    def end_timestamp(self) -> str:
        return _format_timestamp(self.end)


@dataclass
class TranscriptResult:
    segments: list[TranscriptSegment]
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        if not self.segments:
            return 0.0
        return self.segments[-1].end

    @property
    def speakers(self) -> set[str]:
        return {s.speaker for s in self.segments if s.speaker is not None}

    @property
    def unmatched_speakers(self) -> set[str]:
        pattern = re.compile(r"^Speaker \d+$")
        return {s for s in self.speakers if pattern.match(s)}


@dataclass
class SpeakerPool:
    podcast: str
    speakers: dict[str, list[Path]] = field(default_factory=dict)


def _format_timestamp(seconds: float) -> str:
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"
