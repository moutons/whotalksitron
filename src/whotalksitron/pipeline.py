from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from whotalksitron.backends import Backend
from whotalksitron.config import Config
from whotalksitron.models import SpeakerPool, TranscriptResult
from whotalksitron.output import render_transcript
from whotalksitron.progress import ProgressReporter

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    pass


class PreprocessingError(Exception):
    pass


@dataclass
class PipelineResult:
    exit_code: int
    transcript: TranscriptResult | None = None
    output_path: Path | None = None
    warnings: list[str] | None = None


class Pipeline:
    def __init__(self, config: Config) -> None:
        self._config = config

    def run(
        self,
        audio_path: Path,
        output_path: Path,
        backend: Backend,
        podcast: str | None,
        speakers: SpeakerPool | None,
        progress: ProgressReporter | None = None,
    ) -> PipelineResult:
        warnings: list[str] = []

        # Stage 1: Validate
        try:
            info = validate_audio(audio_path)
            if progress:
                size_mb = info["size_bytes"] / (1024 * 1024)
                progress.stage_complete(
                    "validate", f"{audio_path.name}, {size_mb:.1f}MB"
                )
        except ValidationError:
            raise

        # Stage 2: Preprocess
        processed_path = audio_path
        logger.debug("Checking if conversion needed for %s", audio_path.suffix)
        if self._needs_conversion(audio_path, backend):
            if not check_ffmpeg():
                raise PreprocessingError(
                    "ffmpeg is required to convert audio files. "
                    "Install: brew install ffmpeg"
                )
            processed_path = self._convert_audio(audio_path)
            if progress:
                progress.stage_complete("preprocess", "converted to WAV")
        else:
            if progress:
                progress.stage_complete("preprocess", "skipped, native format")

        # Stage 3: Transcribe
        transcript = backend.transcribe(
            processed_path,
            speakers=speakers,
            progress=progress,
        )

        if not transcript.segments:
            logger.warning(
                "Backend returned no transcript segments. "
                "The response may have been empty or in an unexpected format."
            )
            warnings.append(
                "No transcript segments were produced. "
                "Try --log-level debug for details."
            )

        # Stage 4: Voiceprint matching
        if speakers and speakers.speakers:
            if progress:
                progress.update("voiceprint", 0, "matching speakers")
            transcript = self._match_voiceprints(
                transcript, speakers, backend, progress
            )
        else:
            if progress:
                progress.stage_complete("voiceprint", "skipped, no speakers enrolled")

        # Stage 5: Format
        if progress:
            progress.update("format", 0, "rendering markdown")
        markdown = render_transcript(
            transcript,
            source_file=audio_path.name,
            podcast=podcast,
        )
        if progress:
            progress.stage_complete("format", "markdown rendered")

        # Stage 6: Write
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown)
        if progress:
            progress.stage_complete("write", str(output_path))

        logger.info("Transcript written to %s", output_path)

        exit_code = 0
        if warnings:
            exit_code = 3

        return PipelineResult(
            exit_code=exit_code,
            transcript=transcript,
            output_path=output_path,
            warnings=warnings,
        )

    def _needs_conversion(self, audio_path: Path, backend: Backend) -> bool:
        gemini_formats = {".mp3", ".wav", ".flac", ".m4a", ".webm", ".ogg"}
        common_formats = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".opus"}
        suffix = audio_path.suffix.lower()
        if backend.name == "gemini":
            return suffix not in gemini_formats
        if backend.name == "pyannote":
            return suffix != ".wav"
        # whisper and unknown backends handle common audio formats natively
        return suffix not in common_formats

    def _convert_audio(self, audio_path: Path) -> Path:
        output = audio_path.with_suffix(".converted.wav")
        cmd = [
            "ffmpeg",
            "-i",
            str(audio_path),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-y",
            str(output),
        ]
        logger.debug("Running: %s", " ".join(cmd))
        result = subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise PreprocessingError(f"ffmpeg conversion failed: {result.stderr[:500]}")
        return output

    def _match_voiceprints(
        self,
        transcript: TranscriptResult,
        speakers: SpeakerPool,
        backend: Backend,
        progress: ProgressReporter | None,
    ) -> TranscriptResult:
        from whotalksitron.speakers.embeddings import load_embedding
        from whotalksitron.speakers.enrollment import SpeakerStore
        from whotalksitron.speakers.matching import SpeakerEmbeddings, match_speakers

        enrolled: dict = {}
        store = SpeakerStore(self._config.speakers_dir)
        for name in speakers.speakers:
            emb_path = store.embedding_path(name, speakers.podcast)
            emb = load_embedding(emb_path)
            if emb is not None:
                enrolled[name] = emb

        if not enrolled:
            if progress:
                progress.stage_complete("voiceprint", "no embeddings found")
            return transcript

        raw_detected = transcript.metadata.get("speaker_embeddings")
        detected: dict[str, np.ndarray] = {}
        if isinstance(raw_detected, dict):
            for k, v in raw_detected.items():
                if isinstance(k, str) and isinstance(v, np.ndarray):
                    detected[k] = v

        if not detected:
            logger.info(
                "No detected speaker embeddings available. "
                "Voiceprint matching skipped for this backend."
            )
            if progress:
                progress.stage_complete("voiceprint", "no detected embeddings")
            return transcript

        if progress:
            progress.stage_complete(
                "voiceprint",
                f"{len(enrolled)} enrolled, {len(detected)} detected",
            )

        speaker_embeddings = SpeakerEmbeddings(enrolled=enrolled, detected=detected)
        return match_speakers(
            transcript,
            speaker_embeddings,
            self._config.match_threshold,
        )


def validate_audio(path: Path) -> dict:
    if not path.exists():
        raise ValidationError(f"Audio file not found: {path}")
    stat = path.stat()
    if stat.st_size == 0:
        raise ValidationError(f"Audio file is empty: {path}")
    return {
        "path": path,
        "size_bytes": stat.st_size,
        "suffix": path.suffix,
    }


def check_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None
