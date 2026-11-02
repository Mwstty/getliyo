from app.utils.name_template import render_template, validate_template
import datetime


def test_simple_title():
    assert render_template("{title}", title="Kedi Videosu") == "Kedi Videosu"


def test_platform_title():
    out = render_template("{platform} - {title}", title="Video", platform="YouTube")
    assert out == "YouTube - Video"


def test_missing_uploader_cleans_up_separator():
    out = render_template("{uploader} - {title}", title="Video", uploader="")
    assert out == "Video"


def test_id_token():
    out = render_template("{title} [{id}]", title="Video", media_id="abc123")
    assert out == "Video [abc123]"


def test_date_token_fixed_date():
    out = render_template("{date} - {title}", title="V", when=datetime.date(2026, 9, 27))
    assert out == "2026-09-27 - V"


def test_forbidden_chars_still_sanitized():
    out = render_template("{title}", title='a/b:c*d')
    assert "/" not in out and ":" not in out and "*" not in out


def test_empty_title_gets_fallback():
    out = render_template("{title}", title="")
    assert out == "indirilen_dosya"


def test_validate_template():
    assert validate_template("{title} - {platform}") is True
    assert validate_template("{title} - {bilinmeyen}") is False
    assert validate_template("") is False
    assert validate_template("sabit isim") is True  # token olmasa da gecerli sabit sablon
