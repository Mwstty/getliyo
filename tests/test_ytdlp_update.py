from app.utils.ytdlp_update import YtdlpStatus


def test_newer_detection():
    assert YtdlpStatus("2025.01.01", "2025.02.10").newer
    assert not YtdlpStatus("2025.02.10", "2025.02.10").newer
    assert not YtdlpStatus("2025.02.10", None).newer
