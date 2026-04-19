from __future__ import annotations

import logging
import shutil
import tomllib
from datetime import UTC, datetime
from pathlib import Path

import tomli_w

logger = logging.getLogger(__name__)


class SpeakerStore:
    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir

    def enroll(
        self,
        name: str,
        podcast: str,
        sample_path: Path,
        compute_embedding: bool = True,
    ) -> None:
        import uuid

        speaker_dir = self._speaker_dir(podcast, name)
        samples_dir = speaker_dir / "samples"
        samples_dir.mkdir(parents=True, exist_ok=True)

        uid = uuid.uuid4().hex[:12]
        dest = samples_dir / f"sample-{uid}{sample_path.suffix}"
        shutil.copy2(sample_path, dest)

        self._write_meta(name, podcast)

        if compute_embedding:
            self._update_embedding(name, podcast)

    def import_speaker(self, name: str, *, from_podcast: str, to_podcast: str) -> None:
        src = self._speaker_dir(from_podcast, name)
        if not src.exists():
            raise FileNotFoundError(
                f"Speaker {name!r} not found in podcast {from_podcast!r}"
            )
        dest = self._speaker_dir(to_podcast, name)
        if dest.exists():
            logger.info("Replacing existing speaker %s in %s", name, to_podcast)
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        logger.debug("Copied speaker data %s -> %s", src, dest)

        meta = self.get_meta(name, to_podcast)
        meta["podcast"] = to_podcast
        meta_path = dest / "meta.toml"
        with open(meta_path, "wb") as f:
            tomli_w.dump(meta, f)

    def list_speakers(self, *, podcast: str | None = None) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        if not self._base.exists():
            return result

        podcasts = [self._base / podcast] if podcast else list(self._base.iterdir())
        for podcast_dir in podcasts:
            if not podcast_dir.is_dir():
                continue
            speakers = sorted(d.name for d in podcast_dir.iterdir() if d.is_dir())
            if speakers:
                result[podcast_dir.name] = speakers
        return result

    def get_meta(self, name: str, podcast: str) -> dict:
        meta_path = self._speaker_dir(podcast, name) / "meta.toml"
        if not meta_path.exists():
            return {}
        with open(meta_path, "rb") as f:
            return tomllib.load(f)

    def get_sample_paths(self, name: str, podcast: str) -> list[Path]:
        samples_dir = self._speaker_dir(podcast, name) / "samples"
        if not samples_dir.exists():
            return []
        return sorted(samples_dir.iterdir())

    def embedding_path(self, name: str, podcast: str) -> Path:
        return self._speaker_dir(podcast, name) / "embeddings" / "embedding.npy"

    def rebuild_embeddings(self, name: str, podcast: str) -> None:
        self._update_embedding(name, podcast)

    def _update_embedding(self, name: str, podcast: str) -> None:
        from whotalksitron.speakers.embeddings import (
            average_embeddings,
            get_embedding_computer,
            save_embedding,
        )

        samples = self.get_sample_paths(name, podcast)
        if not samples:
            return

        try:
            computer = get_embedding_computer()
        except Exception:
            logger.warning(
                "No embedding model available. Enroll succeeded but "
                "embedding not computed. Install pyannote for voiceprint matching.",
                exc_info=True,
            )
            return

        embeddings = []
        for sample in samples:
            try:
                emb = computer.compute(sample)
                embeddings.append(emb)
            except Exception:
                logger.warning(
                    "Failed to compute embedding for %s",
                    sample,
                    exc_info=True,
                )

        if embeddings:
            avg = average_embeddings(embeddings)
            emb_path = self.embedding_path(name, podcast)
            save_embedding(avg, emb_path)
            logger.info(
                "Embedding updated for %s/%s from %d samples",
                podcast,
                name,
                len(embeddings),
            )

    def _speaker_dir(self, podcast: str, name: str) -> Path:
        return self._base / podcast / name

    def _write_meta(self, name: str, podcast: str) -> None:
        speaker_dir = self._speaker_dir(podcast, name)
        samples_dir = speaker_dir / "samples"
        sample_count = len(list(samples_dir.iterdir())) if samples_dir.exists() else 0

        meta = {
            "name": name,
            "podcast": podcast,
            "sample_count": sample_count,
            "enrolled_at": datetime.now(UTC).isoformat(),
        }
        meta_path = speaker_dir / "meta.toml"
        with open(meta_path, "wb") as f:
            tomli_w.dump(meta, f)


def enroll_speaker(
    name: str, podcast: str, sample_path: Path, speakers_dir: Path
) -> None:
    store = SpeakerStore(speakers_dir)
    store.enroll(name, podcast, sample_path)


def import_speaker(
    name: str, from_podcast: str, to_podcast: str, speakers_dir: Path
) -> None:
    store = SpeakerStore(speakers_dir)
    store.import_speaker(name, from_podcast=from_podcast, to_podcast=to_podcast)


def list_speakers(
    speakers_dir: Path, podcast: str | None = None
) -> dict[str, list[str]]:
    store = SpeakerStore(speakers_dir)
    return store.list_speakers(podcast=podcast)
