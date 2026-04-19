from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

import numpy as np

logger = logging.getLogger(__name__)


class EmbeddingComputer(Protocol):
    def compute(self, audio_path: Path) -> np.ndarray: ...
    def is_available(self) -> bool: ...


def save_embedding(embedding: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, embedding)


def load_embedding(path: Path) -> np.ndarray | None:
    if not path.exists():
        return None
    return np.load(path)


def average_embeddings(embeddings: list[np.ndarray]) -> np.ndarray:
    if not embeddings:
        raise ValueError("Need at least one embedding to average")
    avg = np.mean(embeddings, axis=0)
    norm = np.linalg.norm(avg)
    if norm > 0:
        avg = avg / norm
    return avg.astype(np.float32)


def get_embedding_computer() -> EmbeddingComputer:
    try:
        return _PyAnnoteEmbedder()
    except ImportError:
        logger.info("pyannote not available, using ONNX fallback")
        return _OnnxEmbedder()


class _PyAnnoteEmbedder:
    def __init__(self) -> None:
        from pyannote.audio import Inference, Model

        self._model = Model.from_pretrained("pyannote/wespeaker-voxceleb-resnet34-LM")
        self._inference = Inference(self._model, window="whole")

    def compute(self, audio_path: Path) -> np.ndarray:
        embedding = self._inference(str(audio_path))
        return np.array(embedding).flatten().astype(np.float32)

    def is_available(self) -> bool:
        return True


class _OnnxEmbedder:
    def __init__(self) -> None:
        pass

    def compute(self, audio_path: Path) -> np.ndarray:
        raise NotImplementedError(
            "ONNX embedding fallback is not yet implemented. "
            "Install pyannote: uv tool install whotalksitron --with local"
        )

    def is_available(self) -> bool:
        return False
