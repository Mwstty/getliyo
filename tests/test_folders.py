import datetime
from pathlib import Path

from app.utils.folders import organized_dir

B = Path("/dl")


def test_flat_by_default():
    assert organized_dir(B, platform="YouTube", kind="video") == B


def test_platform_type_date():
    d = organized_dir(B, platform="YouTube", kind="video", by_platform=True, by_type=True, by_date=True,
                      when=datetime.date(2026, 9, 27))
    assert d == B / "YouTube" / "Video" / "2026" / "09"


def test_platform_sanitized_no_traversal():
    d = organized_dir(B, platform="../../etc", by_platform=True)
    assert ".." not in d.parts and d.parent == B


def test_unknown_platform_fallback():
    assert organized_dir(B, platform="", by_platform=True) == B / "Diğer"
