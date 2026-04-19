from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import numpy as np

from whotalksitron.models import TranscriptResult, TranscriptSegment

logger = logging.getLogger(__name__)

_GENERIC_PATTERN = re.compile(r"^Speaker \d+$")


@dataclass
class SpeakerEmbeddings:
    enrolled: dict[str, np.ndarray] = field(default_factory=dict)
    detected: dict[str, np.ndarray] = field(default_factory=dict)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def match_speakers(
    result: TranscriptResult,
    speaker_embeddings: SpeakerEmbeddings,
    threshold: float,
) -> TranscriptResult:
    if not speaker_embeddings.enrolled or not speaker_embeddings.detected:
        logger.debug(
            "No embeddings to match (enrolled=%d, detected=%d)",
            len(speaker_embeddings.enrolled),
            len(speaker_embeddings.detected),
        )
        return result

    logger.debug(
        "Matching %d detected speakers against %d enrolled (threshold=%.2f)",
        len(speaker_embeddings.detected),
        len(speaker_embeddings.enrolled),
        threshold,
    )
    label_map: dict[str, str] = {}
    for detected_name, detected_emb in speaker_embeddings.detected.items():
        best_name: str | None = None
        best_score = threshold

        for enrolled_name, enrolled_emb in speaker_embeddings.enrolled.items():
            score = cosine_similarity(detected_emb, enrolled_emb)
            logger.debug(
                "Similarity %s <-> %s: %.3f",
                detected_name,
                enrolled_name,
                score,
            )
            if score > best_score:
                best_score = score
                best_name = enrolled_name

        if best_name:
            label_map[detected_name] = best_name
            logger.info(
                "Matched %s -> %s (score: %.3f)",
                detected_name,
                best_name,
                best_score,
            )

    if not label_map:
        logger.info("No speakers matched above threshold %.2f", threshold)
        return result

    new_segments = []
    for seg in result.segments:
        speaker = seg.speaker
        if speaker and _GENERIC_PATTERN.match(speaker) and speaker in label_map:
            speaker = label_map[speaker]
        new_segments.append(
            TranscriptSegment(
                start=seg.start,
                end=seg.end,
                text=seg.text,
                speaker=speaker,
            )
        )

    return TranscriptResult(segments=new_segments, metadata=result.metadata)
