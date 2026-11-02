import pytest

from app.downloaders.platform_detector import detect_platform, resolve_url


@pytest.mark.parametrize(
    "url,name",
    [
        ("https://www.youtube.com/watch?v=x", "YouTube"),
        ("https://youtu.be/x", "YouTube"),
        ("https://www.instagram.com/reel/abc/", "Instagram"),
        ("https://x.com/user/status/1", "X"),
        ("https://twitter.com/user/status/1", "X"),
        ("https://www.tiktok.com/@u/video/1", "TikTok"),
        ("https://www.facebook.com/watch?v=1", "Facebook"),
        ("https://www.reddit.com/r/a/comments/1/x/", "Reddit"),
        ("https://www.pinterest.com/pin/1/", "Pinterest"),
        ("https://www.twitch.tv/videos/1", "Twitch"),
        ("https://ornek.com/sayfa", "Diğer web sitesi"),
    ],
)
def test_platforms(url, name):
    info = detect_platform(url)
    assert info.name == name and not info.is_direct_media


@pytest.mark.parametrize("url", ["https://a.com/x.mp4", "https://a.com/x.JPG?v=1", "https://a.com/s.mp3", "https://pbs.twimg.com/media/abc?format=jpg&name=small", "https://i.redd.it/abc.png"])
def test_direct(url):
    assert detect_platform(url).is_direct_media


def test_google_images():
    u = "https://www.google.com/imgres?imgurl=https%3A%2F%2Fa.com%2Ffoto.jpg&imgrefurl=https%3A%2F%2Fa.com"
    assert detect_platform(u).name == "Google Images"
    assert resolve_url(u) == "https://a.com/foto.jpg"
    assert resolve_url("https://a.com/x") == "https://a.com/x"


def test_no_fallback_for_social():
    assert not detect_platform("https://www.instagram.com/p/1/").html_fallback
    assert detect_platform("https://www.pinterest.com/pin/1/").html_fallback
