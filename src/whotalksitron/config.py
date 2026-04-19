from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

import tomli_w

logger = logging.getLogger(__name__)


@dataclass
class Config:
    backend: str = "auto"
    log_level: str = "info"
    log_format: str = "text"
    progress: bool = False

    gemini_api_key: str = ""
    gemini_use_adc: bool = False
    gemini_project: str = ""
    gemini_location: str = ""
    gemini_gcs_bucket: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_keychain_account: str = "vertex"
    gemini_keychain_service: str = "vertex-apikey"
    gemini_op_reference: str = ""

    pyannote_whisper_model: str = "large-v3"
    pyannote_diarization_model: str = "pyannote/speaker-diarization-3.1"
    pyannote_device: str = "auto"

    whisper_endpoint: str = "http://localhost:1234/v1"
    whisper_model: str = "whisper-large-v3"

    match_threshold: float = 0.7
    timestamp_format: str = "HH:MM:SS"

    @property
    def config_dir(self) -> Path:
        return Path.home() / ".config" / "whotalksitron"

    @property
    def speakers_dir(self) -> Path:
        return self.config_dir / "speakers"

    @property
    def staging_dir(self) -> Path:
        return self.config_dir / "staging"

    @classmethod
    def from_dict(cls, data: dict) -> Config:
        cfg = cls()
        defaults = data.get("defaults", {})
        gemini = data.get("gemini", {})
        pyannote = data.get("pyannote", {})
        whisper = data.get("whisper", {})
        speakers = data.get("speakers", {})
        output = data.get("output", {})

        if "backend" in defaults:
            cfg.backend = defaults["backend"]
        if "log_level" in defaults:
            cfg.log_level = defaults["log_level"]
        if "log_format" in defaults:
            cfg.log_format = defaults["log_format"]
        if "progress" in defaults:
            cfg.progress = defaults["progress"]

        if "api_key" in gemini:
            cfg.gemini_api_key = gemini["api_key"]
        if "use_adc" in gemini:
            cfg.gemini_use_adc = gemini["use_adc"]
        if "project" in gemini:
            cfg.gemini_project = gemini["project"]
        if "location" in gemini:
            cfg.gemini_location = gemini["location"]
        if "gcs_bucket" in gemini:
            cfg.gemini_gcs_bucket = gemini["gcs_bucket"]
        if "model" in gemini:
            cfg.gemini_model = gemini["model"]
        if "keychain_account" in gemini:
            cfg.gemini_keychain_account = gemini["keychain_account"]
        if "keychain_service" in gemini:
            cfg.gemini_keychain_service = gemini["keychain_service"]
        if "op_reference" in gemini:
            cfg.gemini_op_reference = gemini["op_reference"]

        if "whisper_model" in pyannote:
            cfg.pyannote_whisper_model = pyannote["whisper_model"]
        if "diarization_model" in pyannote:
            cfg.pyannote_diarization_model = pyannote["diarization_model"]
        if "device" in pyannote:
            cfg.pyannote_device = pyannote["device"]

        if "endpoint" in whisper:
            cfg.whisper_endpoint = whisper["endpoint"]
        if "model" in whisper:
            cfg.whisper_model = whisper["model"]

        if "match_threshold" in speakers:
            cfg.match_threshold = speakers["match_threshold"]

        if "timestamp_format" in output:
            cfg.timestamp_format = output["timestamp_format"]

        return cfg

    @classmethod
    def from_file(cls, path: Path) -> Config:
        if not path.exists():
            logger.debug("No config file at %s, using defaults", path)
            return cls()
        logger.debug("Loading config from %s", path)
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return cls.from_dict(data)

    def show(self) -> str:
        lines = []
        lines.append(f"backend = {self.backend!r}")
        lines.append(f"log_level = {self.log_level!r}")
        lines.append(f"progress = {self.progress!r}")

        masked_key = _mask_secret(self.gemini_api_key)
        lines.append(f"gemini.api_key = {masked_key!r}")
        lines.append(f"gemini.use_adc = {self.gemini_use_adc!r}")
        if self.gemini_project:
            lines.append(f"gemini.project = {self.gemini_project!r}")
        if self.gemini_location:
            lines.append(f"gemini.location = {self.gemini_location!r}")
        if self.gemini_gcs_bucket:
            lines.append(f"gemini.gcs_bucket = {self.gemini_gcs_bucket!r}")
        lines.append(f"gemini.model = {self.gemini_model!r}")

        lines.append(f"pyannote.whisper_model = {self.pyannote_whisper_model!r}")
        lines.append(f"pyannote.device = {self.pyannote_device!r}")

        lines.append(f"whisper.endpoint = {self.whisper_endpoint!r}")
        lines.append(f"whisper.model = {self.whisper_model!r}")

        lines.append(f"speakers.match_threshold = {self.match_threshold!r}")
        return "\n".join(lines)

    def write_default(self, path: Path) -> None:
        data = {
            "defaults": {
                "backend": self.backend,
                "log_level": self.log_level,
                "progress": self.progress,
            },
            "gemini": {
                "api_key": "",
                "use_adc": False,
                "project": "",
                "location": "",
                "gcs_bucket": "",
                "model": self.gemini_model,
                "keychain_account": self.gemini_keychain_account,
                "keychain_service": self.gemini_keychain_service,
                "op_reference": "",
            },
            "pyannote": {
                "whisper_model": self.pyannote_whisper_model,
                "diarization_model": self.pyannote_diarization_model,
                "device": self.pyannote_device,
            },
            "whisper": {
                "endpoint": self.whisper_endpoint,
                "model": self.whisper_model,
            },
            "speakers": {
                "match_threshold": self.match_threshold,
            },
            "output": {
                "timestamp_format": self.timestamp_format,
            },
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            tomli_w.dump(data, f)


def load_config(
    config_path: Path | None,
    cli_overrides: dict[str, object],
) -> Config:
    if config_path is None:
        config_path = Path.home() / ".config" / "whotalksitron" / "config.toml"

    cfg = Config.from_file(config_path)

    # Keychain / 1Password: resolve API key if not set in config
    if not cfg.gemini_api_key:
        cfg.gemini_api_key = _resolve_secret(cfg) or ""

    str_env_map = {
        "GEMINI_API_KEY": "gemini_api_key",
        "GOOGLE_CLOUD_API_KEY": "gemini_api_key",
        "GOOGLE_CLOUD_PROJECT": "gemini_project",
        "GOOGLE_CLOUD_LOCATION": "gemini_location",
        "GOOGLE_CLOUD_STORAGE_BUCKET": "gemini_gcs_bucket",
        "WHOTALKSITRON_BACKEND": "backend",
        "WHOTALKSITRON_LOG_LEVEL": "log_level",
    }
    for env_var, attr in str_env_map.items():
        val = os.environ.get(env_var)
        if val is not None:
            if attr == "gemini_api_key":
                logger.debug("Setting %s from %s", attr, env_var)
            else:
                logger.debug("Setting %s=%s from %s", attr, val, env_var)
            setattr(cfg, attr, val)

    vertexai_env = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI")
    if vertexai_env is not None:
        cfg.gemini_use_adc = vertexai_env.lower() in ("1", "true", "yes")
        logger.debug(
            "Setting gemini_use_adc=%s from GOOGLE_GENAI_USE_VERTEXAI=%s",
            cfg.gemini_use_adc,
            vertexai_env,
        )

    for key, val in cli_overrides.items():
        if val is not None and hasattr(cfg, key):
            setattr(cfg, key, val)

    return cfg


def _resolve_secret(cfg: Config) -> str | None:
    import subprocess

    keychain_account = cfg.gemini_keychain_account
    keychain_service = cfg.gemini_keychain_service
    try:
        result = subprocess.run(  # noqa: S603
            [  # noqa: S607
                "security",
                "find-generic-password",
                "-a",
                keychain_account,
                "-s",
                keychain_service,
                "-w",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            logger.debug(
                "API key loaded from macOS Keychain (%s/%s)",
                keychain_service,
                keychain_account,
            )
            return result.stdout.strip()
        logger.debug(
            "Keychain lookup returned %d for %s/%s",
            result.returncode,
            keychain_service,
            keychain_account,
        )
    except FileNotFoundError:
        logger.debug("security command not found, skipping Keychain")
    except subprocess.TimeoutExpired:
        logger.debug("Keychain lookup timed out")

    op_ref = cfg.gemini_op_reference or None
    if op_ref:
        try:
            result = subprocess.run(  # noqa: S603
                ["op", "read", op_ref],  # noqa: S607
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                logger.debug("API key loaded from 1Password")
                return result.stdout.strip()
            logger.debug("1Password lookup returned %d", result.returncode)
        except FileNotFoundError:
            logger.debug("op command not found, skipping 1Password")
        except subprocess.TimeoutExpired:
            logger.debug("1Password lookup timed out")

    return None


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return value[:4] + "..." + value[-3:]
