from pathlib import Path

from app.utils.filename import (
    build_base_name,
    existing_files,
    resolve_base_name,
    sanitize_filename,
)


def test_forbidden_chars_removed():
    out = sanitize_filename('a\\b/c:d*e?f"g<h>i|j')
    assert not any(c in out for c in '\\/:*?"<>|')


def test_long_name_truncated():
    assert len(sanitize_filename("x" * 500, max_len=100)) == 100


def test_reserved_and_empty():
    assert sanitize_filename("CON").startswith("_")
    assert sanitize_filename("...   ") == "indirilen_dosya"
    assert sanitize_filename("") == "indirilen_dosya"


def test_trailing_dot_space_stripped():
    assert sanitize_filename("video. ") == "video"


def test_naming_styles():
    assert build_base_name("T", "YouTube", "abc", "platform_title") == "YouTube - T"
    assert build_base_name("T", "YouTube", "abc", "title_id") == "T [abc]"
    assert build_base_name("T") == "T"


def test_conflict_policies(tmp_path: Path):
    (tmp_path / "video.mp4").write_bytes(b"x")
    assert resolve_base_name(tmp_path, "video", "overwrite") == ("video", None)
    base, skip = resolve_base_name(tmp_path, "video", "skip")
    assert skip is not None and base == "video"
    assert resolve_base_name(tmp_path, "video", "new") == ("video (2)", None)
    (tmp_path / "video (2).mp4").write_bytes(b"x")
    assert resolve_base_name(tmp_path, "video", "new")[0] == "video (3)"
    assert resolve_base_name(tmp_path, "yeni", "skip") == ("yeni", None)


def test_part_files_ignored(tmp_path: Path):
    (tmp_path / "a.mp4.part").write_bytes(b"x")
    assert existing_files(tmp_path, "a") == []
