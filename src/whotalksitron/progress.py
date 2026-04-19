from __future__ import annotations

import json
import sys
from typing import IO, Protocol


class ProgressCallback(Protocol):
    def update(self, stage: str, percent: int, detail: str) -> None: ...
    def stage_complete(self, stage: str, detail: str) -> None: ...


class ProgressReporter:
    def __init__(
        self,
        stream: IO[str] | None = None,
        enabled: bool = True,
    ) -> None:
        self._stream = stream or sys.stderr
        self._enabled = enabled

    def update(self, stage: str, percent: int, detail: str) -> None:
        if not self._enabled:
            return
        line = json.dumps(
            {"stage": stage, "percent": percent, "detail": detail},
            ensure_ascii=False,
        )
        self._stream.write(line + "\n")
        self._stream.flush()

    def stage_complete(self, stage: str, detail: str) -> None:
        self.update(stage, 100, detail)
