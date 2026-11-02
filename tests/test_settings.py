import json

import pytest

from app.settings.settings_manager import SettingsManager


def test_defaults_and_roundtrip(tmp_path):
    p = tmp_path / "settings.json"
    s = SettingsManager(p)
    assert s.get("default_quality") == "best"
    s.set("default_quality", "720")
    s2 = SettingsManager(p)
    assert s2.get("default_quality") == "720"


def test_invalid_values_ignored(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"default_quality": "999", "naming_template": "{platform} - {title}", "junk": 1}), encoding="utf-8")
    s = SettingsManager(p)
    assert s.get("default_quality") == "best"
    assert s.get("naming_template") == "{platform} - {title}"


def test_corrupt_file(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{bozuk", encoding="utf-8")
    assert SettingsManager(p).get("conflict_behavior") == "new"


def test_set_rejects_bad(tmp_path):
    s = SettingsManager(tmp_path / "s.json")
    with pytest.raises(ValueError):
        s.set("default_quality", "nope")
    with pytest.raises(ValueError):
        s.set("naming_template", "{bilinmeyen_token}")
    with pytest.raises(KeyError):
        s.set("nokey", 1)


def test_download_dir_default(tmp_path):
    s = SettingsManager(tmp_path / "s.json")
    assert s.download_dir.name == "getliyo"
    s.set("download_dir", str(tmp_path))
    assert s.download_dir == tmp_path


def test_new_settings_defaults(tmp_path):
    s = SettingsManager(tmp_path / "s.json")
    assert s.get("naming_template") == "{title}"
    assert s.get("max_concurrent_downloads") == "3"
    assert s.get("use_recycle_bin") is True
    assert s.get("notifications_enabled") is True
    assert s.get("clipboard_detect_enabled") is True


def test_naming_template_roundtrip(tmp_path):
    p = tmp_path / "s.json"
    s = SettingsManager(p)
    s.set("naming_template", "{platform} - {title} [{id}]")
    s2 = SettingsManager(p)
    assert s2.get("naming_template") == "{platform} - {title} [{id}]"


def test_bool_and_concurrency_settings(tmp_path):
    s = SettingsManager(tmp_path / "s.json")
    s.set("max_concurrent_downloads", "5")
    s.set("use_recycle_bin", False)
    s.set("notifications_enabled", False)
    assert s.get("max_concurrent_downloads") == "5"
    assert s.get("use_recycle_bin") is False
    assert s.get("notifications_enabled") is False
