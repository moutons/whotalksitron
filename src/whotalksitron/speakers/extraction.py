from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from whotalksitron.models import TranscriptSegment

logger = logging.getLogger(__name__)


@dataclass
class CandidateSample:
    start: float
    end: float
    speaker: str
    score: float

    @property
    def duration(self) -> float:
        return self.end - self.start


def group_segments_by_speaker(
    segments: list[TranscriptSegment],
) -> dict[str, list[TranscriptSegment]]:
    groups: dict[str, list[TranscriptSegment]] = {}
    for seg in segments:
        if seg.speaker is None:
            continue
        groups.setdefault(seg.speaker, []).append(seg)
    return groups


def score_segment(seg: TranscriptSegment, total_duration: float) -> float:
    duration_score = min(seg.duration / 15.0, 1.0)

    if total_duration > 0:
        position = (seg.start + seg.end) / 2.0 / total_duration
        diversity_score = 1.0 - abs(position - 0.5) * 0.2
    else:
        diversity_score = 1.0

    length_penalty = 0.0 if seg.duration >= 10.0 else (seg.duration - 10.0) * 0.1

    return duration_score + diversity_score + length_penalty


def find_candidates(
    segments: list[TranscriptSegment],
    total_duration: float,
    max_candidates: int = 3,
) -> list[CandidateSample]:
    scored = []
    for seg in segments:
        s = score_segment(seg, total_duration)
        scored.append(
            CandidateSample(
                start=seg.start,
                end=seg.end,
                speaker=seg.speaker or "Unknown",
                score=s,
            )
        )

    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[:max_candidates]


def extract_audio_clip(
    source_path: Path,
    output_path: Path,
    start: float,
    duration: float,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-i",
        str(source_path),
        "-ss",
        str(start),
        "-t",
        str(duration),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-y",
        str(output_path),
    ]
    logger.debug("Extracting clip: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg clip extraction failed: {result.stderr[:300]}")
    return output_path


def extract_samples_for_speakers(
    audio_path: Path,
    segments: list[TranscriptSegment],
    output_dir: Path,
    max_candidates: int = 3,
) -> dict[str, list[Path]]:
    groups = group_segments_by_speaker(segments)
    total_duration = segments[-1].end if segments else 0.0

    extracted: dict[str, list[Path]] = {}
    for speaker, speaker_segments in groups.items():
        candidates = find_candidates(
            speaker_segments,
            total_duration,
            max_candidates,
        )
        speaker_dir = output_dir / _safe_dirname(speaker)
        paths: list[Path] = []
        for i, cand in enumerate(candidates):
            clip_path = speaker_dir / f"sample-{i + 1:03d}.wav"
            extract_audio_clip(
                audio_path,
                clip_path,
                start=cand.start,
                duration=cand.duration,
            )
            paths.append(clip_path)
            logger.info(
                "Extracted %s sample %d: %.1fs from %s",
                speaker,
                i + 1,
                cand.duration,
                _format_time(cand.start),
            )
        extracted[speaker] = paths

    return extracted


def _safe_dirname(speaker: str) -> str:
    return speaker.lower().replace(" ", "-")


def _format_time(seconds: float) -> str:
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    s = int(seconds) % 60
    return f"{h:02d}:{m:02d}:{s:02d}"
