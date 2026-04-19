from __future__ import annotations

import logging
from pathlib import Path

from whotalksitron.config import Config
from whotalksitron.models import SpeakerPool, TranscriptResult, TranscriptSegment
from whotalksitron.progress import ProgressCallback

logger = logging.getLogger(__name__)


class PyAnnoteBackend:
    name = "pyannote"

    def __init__(self, config: Config) -> None:
        self._config = config

    def transcribe(
        self,
        audio_path: str | Path,
        *,
        speakers: SpeakerPool | None = None,
        progress: ProgressCallback | None = None,
    ) -> TranscriptResult:
        import torch
        import whisper
        from pyannote.audio import Pipeline as DiarizationPipeline

        audio_path = Path(audio_path)
        device = _select_device(self._config.pyannote_device)
        logger.info("Using device: %s", device)

        if progress:
            progress.update("transcribe", 0, "loading Whisper model")

        whisper_model = whisper.load_model(
            self._config.pyannote_whisper_model,
            device=device,
        )

        if progress:
            progress.update("transcribe", 20, "transcribing audio")

        whisper_result = whisper_model.transcribe(str(audio_path))
        transcription = [
            TranscriptSegment(
                start=seg["start"],
                end=seg["end"],
                text=seg["text"].strip(),
            )
            for seg in whisper_result.get("segments", [])
        ]

        if progress:
            progress.stage_complete("transcribe", f"{len(transcription)} segments")

        if progress:
            progress.update("diarize", 0, "loading diarization model")

        diarization_pipeline = DiarizationPipeline.from_pretrained(
            self._config.pyannote_diarization_model,
        )
        if device != "cpu":
            diarization_pipeline.to(torch.device(device))

        if progress:
            progress.update("diarize", 30, "diarizing audio")

        diarization_result = diarization_pipeline(str(audio_path))

        diarization_regions = [
            (turn.start, turn.end, speaker)
            for turn, _, speaker in diarization_result.itertracks(yield_label=True)
        ]

        if progress:
            progress.stage_complete(
                "diarize", f"{len(diarization_regions)} speaker regions"
            )

        segments = _merge_transcription_and_diarization(
            transcription, diarization_regions
        )

        speaker_embeddings = {}
        if speakers:
            from pyannote.audio import Inference, Model

            emb_model = Model.from_pretrained("pyannote/wespeaker-voxceleb-resnet34-LM")
            emb_inference = Inference(emb_model, window="whole")

            raw_speakers = sorted(set(s for _, _, s in diarization_regions))
            speaker_map = {
                raw: f"Speaker {i + 1}" for i, raw in enumerate(raw_speakers)
            }
            for raw_name, mapped_name in speaker_map.items():
                regions = [(s, e) for s, e, sp in diarization_regions if sp == raw_name]
                if regions:
                    longest = max(regions, key=lambda r: r[1] - r[0])
                    import tempfile

                    from whotalksitron.speakers.extraction import extract_audio_clip

                    with tempfile.NamedTemporaryFile(
                        suffix=".wav", delete=False
                    ) as tmp:
                        clip_path = Path(tmp.name)
                    extract_audio_clip(
                        audio_path,
                        clip_path,
                        start=longest[0],
                        duration=longest[1] - longest[0],
                    )
                    emb = emb_inference(str(clip_path))
                    speaker_embeddings[mapped_name] = emb.flatten()
                    clip_path.unlink(missing_ok=True)

        return TranscriptResult(
            segments=segments,
            metadata={
                "model": self._config.pyannote_whisper_model,
                "diarization_model": self._config.pyannote_diarization_model,
                "backend": "pyannote",
                "device": device,
                "speaker_embeddings": speaker_embeddings,
            },
        )

    def supports_diarization(self) -> bool:
        return True

    def is_available(self) -> bool:
        try:
            import pyannote.audio  # noqa: F401
            import torch  # noqa: F401

            return True
        except (ImportError, AttributeError, Exception):
            return False


def _merge_transcription_and_diarization(
    transcription: list[TranscriptSegment],
    diarization: list[tuple[float, float, str]],
) -> list[TranscriptSegment]:
    if not transcription:
        return []

    raw_speakers = sorted(set(s for _, _, s in diarization))
    speaker_map = {raw: f"Speaker {i + 1}" for i, raw in enumerate(raw_speakers)}

    merged: list[TranscriptSegment] = []
    for seg in transcription:
        speaker = _find_majority_speaker(
            seg.start,
            seg.end,
            diarization,
            speaker_map,
        )
        merged.append(
            TranscriptSegment(
                start=seg.start,
                end=seg.end,
                text=seg.text,
                speaker=speaker,
            )
        )

    return merged


def _find_majority_speaker(
    start: float,
    end: float,
    diarization: list[tuple[float, float, str]],
    speaker_map: dict[str, str],
) -> str | None:
    if not diarization:
        return None

    overlaps: dict[str, float] = {}
    for d_start, d_end, d_speaker in diarization:
        overlap_start = max(start, d_start)
        overlap_end = min(end, d_end)
        overlap = max(0.0, overlap_end - overlap_start)
        if overlap > 0:
            mapped = speaker_map.get(d_speaker, d_speaker)
            overlaps[mapped] = overlaps.get(mapped, 0.0) + overlap

    if not overlaps:
        return None
    return max(overlaps, key=lambda k: overlaps[k])


def _select_device(device_config: str) -> str:
    if device_config != "auto":
        return device_config
    try:
        import torch

        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except (ImportError, AttributeError):
        pass
    return "cpu"
