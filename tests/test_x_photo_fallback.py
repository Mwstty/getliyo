from app.platforms import twitter


class _Resp:
    def __init__(self, data, ok=True):
        self._d, self._ok = data, ok

    def raise_for_status(self):
        if not self._ok:
            raise RuntimeError("http")

    def json(self):
        return self._d


class _Client:
    def __init__(self, routes):
        self.routes = routes

    def get(self, url):
        for key, val in self.routes.items():
            if key in url:
                return val
        return _Resp({}, ok=False)


def test_parse_status():
    assert twitter.parse_status("https://x.com/BADDlESHeIII/status/2104974382409859536/photo/1") == (
        "BADDlESHeIII",
        "2104974382409859536",
    )
    assert twitter.parse_status("https://x.com/home") is None


def test_syndication_photos():
    data = {"mediaDetails": [{"type": "photo", "media_url_https": "https://pbs.twimg.com/media/A.jpg"}]}
    c = _Client({"syndication": _Resp(data)})
    assert twitter.fetch_photo_urls(c, "https://x.com/u/status/123") == ["https://pbs.twimg.com/media/A.jpg"]


def test_fxtwitter_fallback_when_syndication_fails():
    data = {"tweet": {"media": {"all": [{"type": "photo", "url": "https://pbs.twimg.com/media/B.jpg"}]}}}
    c = _Client({"syndication": _Resp({}, ok=False), "fxtwitter": _Resp(data)})
    assert twitter.fetch_photo_urls(c, "https://x.com/u/status/123") == ["https://pbs.twimg.com/media/B.jpg"]


def test_no_photos_returns_empty():
    assert twitter.fetch_photo_urls(_Client({}), "https://x.com/u/status/123") == []


def test_instagram_shortcode_and_embed_parse():
    from app.platforms import instagram

    assert instagram.shortcode("https://www.instagram.com/p/AbC_12-x/?img_index=2") == "AbC_12-x"
    assert instagram.shortcode("https://www.instagram.com/reel/XyZ9/") == "XyZ9"
    assert instagram.shortcode("https://www.instagram.com/stories/u/1/") is None
    page = (
        r'{\"display_url\":\"https:\\/\\/scontent.cdninstagram.com\\/v\\/a1.jpg?x=1\\u0026y=2\",'
        r'\"display_url\":\"https:\\/\\/scontent.cdninstagram.com\\/v\\/a2.jpg?x=1\",'
        r'\"video_url\":\"https:\\/\\/video.cdninstagram.com\\/v\\/m1.mp4?z=1\"}'
    )
    images, videos = instagram.parse_embed(page)
    assert images == [
        "https://scontent.cdninstagram.com/v/a1.jpg?x=1&y=2",
        "https://scontent.cdninstagram.com/v/a2.jpg?x=1",
    ]
    assert videos == ["https://video.cdninstagram.com/v/m1.mp4?z=1"]


def test_instagram_img_tag_fallback():
    from app.platforms import instagram

    page = '<img class="EmbeddedMediaImage" alt="x" src="https://scontent.cdninstagram.com/v/p.jpg?a=1&amp;b=2">'
    assert instagram.parse_embed(page) == (["https://scontent.cdninstagram.com/v/p.jpg?a=1&b=2"], [])


def test_tiktok_photo_post_parse():
    import json

    from app.platforms import tiktok

    item = {
        "id": "7300000000000000001",
        "desc": "deneme",
        "author": {"uniqueId": "kullanici"},
        "imagePost": {
            "images": [
                {"imageURL": {"urlList": ["https://p16.tiktokcdn.com/a.jpeg"]}},
                {"imageURL": {"urlList": ["https://p16.tiktokcdn.com/b.jpeg"]}},
            ]
        },
        "music": {"playUrl": "https://sf16.tiktokcdn.com/m.mp3"},
    }
    data = {"__DEFAULT_SCOPE__": {"webapp.video-detail": {"itemInfo": {"itemStruct": item}}}}
    page = f'<html><script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">{json.dumps(data)}</script></html>'
    post = tiktok.parse_page(page)
    assert post.images == ["https://p16.tiktokcdn.com/a.jpeg", "https://p16.tiktokcdn.com/b.jpeg"]
    assert post.author == "kullanici" and post.audio.endswith("m.mp3")
    assert tiktok.parse_page("<html></html>") is None
