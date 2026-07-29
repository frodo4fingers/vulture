from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from platformdirs import user_config_path
from pydantic import ValidationError

from vulture.i18n import tr
from vulture.models import AppData, utc_now


class StorageError(RuntimeError):
    pass


class AppDataStore:
    def __init__(self, path: Path | None = None) -> None:
        override = os.environ.get("VULTURE_DATA_DIR")
        root = Path(override).expanduser() if override else user_config_path("Vulture", appauthor=False)
        self.path = path or root / "settings.json"

    def load(self) -> AppData:
        if not self.path.exists():
            return AppData()
        try:
            return AppData.model_validate_json(self.path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError) as error:
            raise StorageError(
                tr(
                    "Could not read settings from {path}: {error}",
                    path=self.path,
                    error=error,
                )
            ) from error

    def save(self, data: AppData) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(".tmp")
        try:
            temporary_path.write_text(
                data.model_dump_json(indent=2),
                encoding="utf-8",
            )
            if os.name != "nt":
                temporary_path.chmod(0o600)
            os.replace(temporary_path, self.path)
        except OSError as error:
            raise StorageError(
                tr(
                    "Could not save settings to {path}: {error}",
                    path=self.path,
                    error=error,
                )
            ) from error
        finally:
            temporary_path.unlink(missing_ok=True)

    def prune_history(self, data: AppData, keep_days: int = 7) -> None:
        cutoff = utc_now() - timedelta(days=keep_days)
        data.reminder_history = [
            event for event in data.reminder_history if event.occurred_at >= cutoff
        ]
