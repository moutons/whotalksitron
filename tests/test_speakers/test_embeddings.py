from pathlib import Path

import numpy as np
import pytest

from whotalksitron.speakers.embeddings import (
    EmbeddingComputer,
    average_embeddings,
    load_embedding,
    save_embedding,
)


def test_save_and_load_embedding(tmp_path):
    embedding = np.random.randn(256).astype(np.float32)
    path = tmp_path / "embedding.npy"
    save_embedding(embedding, path)
    loaded = load_embedding(path)
    np.testing.assert_array_almost_equal(embedding, loaded)


def test_load_embedding_missing():
    result = load_embedding(Path("/nonexistent/embedding.npy"))
    assert result is None


def test_average_embeddings_single():
    e = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    result = average_embeddings([e])
    expected = e / np.linalg.norm(e)
    np.testing.assert_array_almost_equal(result, expected)


def test_average_embeddings_multiple():
    e1 = np.array([1.0, 0.0], dtype=np.float32)
    e2 = np.array([0.0, 1.0], dtype=np.float32)
    result = average_embeddings([e1, e2])
    expected = np.array([0.5, 0.5], dtype=np.float32)
    expected = expected / np.linalg.norm(expected)
    np.testing.assert_array_almost_equal(result, expected)


def test_average_embeddings_normalizes():
    e1 = np.array([3.0, 0.0], dtype=np.float32)
    e2 = np.array([3.0, 0.0], dtype=np.float32)
    result = average_embeddings([e1, e2])
    norm = np.linalg.norm(result)
    assert abs(norm - 1.0) < 1e-6


def test_average_embeddings_empty():
    with pytest.raises(ValueError, match="at least one"):
        average_embeddings([])


def test_embedding_computer_protocol():
    assert "compute" in EmbeddingComputer.__protocol_attrs__
    assert "is_available" in EmbeddingComputer.__protocol_attrs__
