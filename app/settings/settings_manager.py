"""settings.json okuma/yazma (%APPDATA%\\getliyo\\settings.json)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.settings.defaults import BUILTIN_DEFAULTS, VALID, load_defaults
from app.utils.logger import get_logger
from app.utils.paths import default_download_dir, settings_file

log = get_logger("settings")


class SettingsManager:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or settings_file()
        self._data: dict[str, Any] = load_defaults()
        self.load()

    def load(self) -> None:
        data = load_defaults()
        try:
            with open(self.path, encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                for key in BUILTIN_DEFAULTS:
                    if key not in loaded:
                        continue
                    value = loaded[key]
                    if key in VALID and value not in VALID[key]:
                        continue
                    if key == "download_dir" and not isinstance(value, str):
                        continue
                    if key == "naming_template":
                        from app.utils.name_template import validate_template

                        if not isinstance(value, str) or not validate_template(value):
                            continue
                    data[key] = value
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            log.exception("settings.json okunamadı, varsayılanlar kullanılıyor")
        self._data = data

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".json.tmp")
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except OSError:
            log.exception("settings.json yazılamadı")

    def get(self, key: str) -> Any:
        return self._data[key]

    def set(self, key: str, value: Any, save: bool = True) -> None:
        if key not in BUILTIN_DEFAULTS:
            raise KeyError(key)
        if key in VALID and value not in VALID[key]:
            raise ValueError(f"Geçersiz değer: {key}={value!r}")
        if key == "naming_template":
            from app.utils.name_template import validate_template

            if not validate_template(str(value)):
                raise ValueError(f"Geçersiz dosya adı şablonu: {value!r}")
        self._data[key] = value
        if save:
            self.save()

    def update(self, values: dict[str, Any]) -> None:
        for key, value in values.items():
            self.set(key, value, save=False)
        self.save()

    @property
    def download_dir(self) -> Path:
        value = (self._data.get("download_dir") or "").strip()
        return Path(value) if value else default_download_dir()
