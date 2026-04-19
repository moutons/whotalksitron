from pathlib import Path

import pytest

from whotalksitron.speakers.enrollment import (
    SpeakerStore,
)


@pytest.fixture
def speaker_dir(tmp_path):
    return tmp_path / "speakers"


@pytest.fixture
def sample_audio(tmp_path) -> Path:
    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"\x00" * 32044)
    return audio


def test_enroll_creates_directory_structure(speaker_dir, sample_audio):
    store = SpeakerStore(speaker_dir)
    store.enroll("matt", "atp", sample_audio, compute_embedding=False)

    speaker_path = speaker_dir / "atp" / "matt"
    assert speaker_path.exists()
    assert (speaker_path / "samples").is_dir()
    assert (speaker_path / "meta.toml").exists()
    assert len(list((speaker_path / "samples").iterdir())) == 1


def test_enroll_multiple_samples(speaker_dir, sample_audio, tmp_path):
    store = SpeakerStore(speaker_dir)
    store.enroll("matt", "atp", sample_audio, compute_embedding=False)

    second_sample = tmp_path / "sample2.wav"
    second_sample.write_bytes(b"\x00" * 32044)
    store.enroll("matt", "atp", second_sample, compute_embedding=False)

    samples_dir = speaker_dir / "atp" / "matt" / "samples"
    assert len(list(samples_dir.iterdir())) == 2


def test_enroll_updates_meta(speaker_dir, sample_audio, tmp_path):
    store = SpeakerStore(speaker_dir)
    store.enroll("matt", "atp", sample_audio, compute_embedding=False)

    meta = store.get_meta("matt", "atp")
    assert meta["name"] == "matt"
    assert meta["podcast"] == "atp"
    assert meta["sample_count"] == 1

    second = tmp_path / "s2.wav"
    second.write_bytes(b"\x00" * 100)
    store.enroll("matt", "atp", second, compute_embedding=False)

    meta = store.get_meta("matt", "atp")
    assert meta["sample_count"] == 2


def test_list_speakers_empty(speaker_dir):
    store = SpeakerStore(speaker_dir)
    assert store.list_speakers() == {}
    assert store.list_speakers(podcast="atp") == {}


def test_list_speakers_by_podcast(speaker_dir, sample_audio, tmp_path):
    store = SpeakerStore(speaker_dir)
    store.enroll("matt", "atp", sample_audio, compute_embedding=False)

    second = tmp_path / "s2.wav"
    second.write_bytes(b"\x00" * 100)
    store.enroll("casey", "atp", second, compute_embedding=False)

    third = tmp_path / "s3.wav"
    third.write_bytes(b"\x00" * 100)
    store.enroll("gruber", "talkshow", third, compute_embedding=False)

    all_speakers = store.list_speakers()
    assert "atp" in all_speakers
    assert "talkshow" in all_speakers
    assert set(all_speakers["atp"]) == {"matt", "casey"}
    assert all_speakers["talkshow"] == ["gruber"]

    atp_only = store.list_speakers(podcast="atp")
    assert "atp" in atp_only
    assert "talkshow" not in atp_only


def test_import_speaker(speaker_dir, sample_audio):
    store = SpeakerStore(speaker_dir)
    store.enroll("matt", "atp", sample_audio, compute_embedding=False)

    store.import_speaker("matt", from_podcast="atp", to_podcast="talkshow")

    assert (speaker_dir / "talkshow" / "matt" / "samples").is_dir()
    assert (speaker_dir / "talkshow" / "matt" / "meta.toml").exists()
    assert (speaker_dir / "atp" / "matt" / "samples").is_dir()


def test_import_speaker_not_found(speaker_dir):
    store = SpeakerStore(speaker_dir)
    with pytest.raises(FileNotFoundError, match="matt"):
        store.import_speaker("matt", from_podcast="atp", to_podcast="talkshow")


def test_embedding_path(speaker_dir):
    store = SpeakerStore(speaker_dir)
    path = store.embedding_path("matt", "atp")
    assert path == speaker_dir / "atp" / "matt" / "embeddings" / "embedding.npy"


def test_get_sample_paths(speaker_dir, sample_audio, tmp_path):
    store = SpeakerStore(speaker_dir)
    store.enroll("matt", "atp", sample_audio, compute_embedding=False)

    second = tmp_path / "s2.wav"
    second.write_bytes(b"\x00" * 100)
    store.enroll("matt", "atp", second, compute_embedding=False)

    paths = store.get_sample_paths("matt", "atp")
    assert len(paths) == 2
    assert all(p.exists() for p in paths)
