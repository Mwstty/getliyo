from app.platforms.twitter import strip_media_suffix


def test_photo_suffix_stripped():
    url, idx = strip_media_suffix("https://x.com/user/status/12345/photo/2")
    assert url == "https://x.com/user/status/12345"
    assert idx == 2


def test_video_suffix_stripped():
    url, idx = strip_media_suffix("https://twitter.com/user/status/12345/video/1")
    assert url == "https://twitter.com/user/status/12345"
    assert idx == 1


def test_www_and_query_and_trailing_slash():
    url, idx = strip_media_suffix("https://www.x.com/user/status/12345/photo/3/?s=20")
    assert url == "https://www.x.com/user/status/12345"
    assert idx == 3
    url2, idx2 = strip_media_suffix("https://x.com/user/status/12345/photo/1/")
    assert url2 == "https://x.com/user/status/12345"
    assert idx2 == 1


def test_plain_status_url_unchanged():
    url, idx = strip_media_suffix("https://x.com/user/status/12345")
    assert url == "https://x.com/user/status/12345"
    assert idx is None


def test_unrelated_url_unchanged():
    url, idx = strip_media_suffix("https://www.youtube.com/watch?v=abc")
    assert url == "https://www.youtube.com/watch?v=abc"
    assert idx is None
