"""Web sitesi: kırık link, meta etiketleri, SEO dosyaları, 404, sıkıştırma."""
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlsplit

import pytest
from fastapi.testclient import TestClient

from server.app import WEB_DIR, create_app
from server.config import Config
from tests.test_server import FakeManager


@pytest.fixture
def client(tmp_path):
    cfg = Config(data_dir=tmp_path, download_dir=tmp_path / "dl", api_keys=frozenset(), secret=b"s" * 32,
                 site_url="https://getliyo.example")
    (tmp_path / "dl").mkdir()
    with TestClient(create_app(cfg, FakeManager())) as c:
        yield c


class Collector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs, self.ids, self.imgs, self.metas = [], set(), [], {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.ids.add(a["id"])
        if tag in ("a", "link") and a.get("href"):
            self.refs.append(a["href"])
        if tag in ("script", "img") and a.get("src"):
            self.refs.append(a["src"])
        if tag == "img":
            self.imgs.append(a)
        if tag == "meta":
            key = a.get("name") or a.get("property")
            if key:
                self.metas[key] = a.get("content", "")


def html_pages():
    return sorted(p for p in WEB_DIR.rglob("*.html"))


@pytest.mark.parametrize("page", html_pages(), ids=lambda p: str(p.relative_to(WEB_DIR)))
def test_no_broken_internal_links(page, client):
    parser = Collector()
    parser.feed(page.read_text(encoding="utf-8"))
    rel = "/" + page.relative_to(WEB_DIR).as_posix()
    for ref in parser.refs:
        if ref.startswith(("mailto:", "tel:", "javascript:")) or "{{" in ref and not ref.startswith("{{SITE_URL}}"):
            continue
        ref = ref.replace("{{SITE_URL}}", "")
        url = urlsplit(urljoin(rel, ref))
        if url.scheme in ("http", "https") and url.netloc:
            continue  # dış bağlantılar ağa çıkmadan atlanır
        if not url.path:
            continue
        r = client.get(url.path)
        assert r.status_code == 200, f"{rel} -> {ref} ({r.status_code})"
    # sayfa içi çapalar
    for ref in parser.refs:
        base, frag = urldefrag(ref)
        if frag and not base:
            assert frag in parser.ids or frag == "cerez", f"{rel}: #{frag} hedefi yok"


@pytest.mark.parametrize("page", html_pages(), ids=lambda p: str(p.relative_to(WEB_DIR)))
def test_meta_basics(page):
    text = page.read_text(encoding="utf-8")
    assert "<title>" in text and "lang=" in text and 'name="viewport"' in text
    if page.name != "404.html":
        assert 'name="description"' in text and 'rel="canonical"' in text
    parser = Collector()
    parser.feed(text)
    for img in parser.imgs:
        assert "alt" in img, f"{page.name}: alt eksik"


def test_home_has_social_tags(client):
    parser = Collector()
    parser.feed(client.get("/tr/").text)
    for key in ("og:title", "og:description", "og:image", "og:url", "twitter:card"):
        assert parser.metas.get(key), key
    assert parser.metas["og:image"] == "https://getliyo.example/og.png"
    assert client.get("/og.png").headers["content-type"] == "image/png"


def test_canonical_filled(client):
    html = client.get("/tr/").text
    assert '<link rel="canonical" href="https://getliyo.example/tr/">' in html and "{{" not in html


def test_robots_sitemap_llms(client):
    robots = client.get("/robots.txt")
    assert robots.status_code == 200 and "Disallow: /api/" in robots.text
    assert "Sitemap: https://getliyo.example/sitemap.xml" in robots.text
    sitemap = client.get("/sitemap.xml")
    assert "<loc>https://getliyo.example/en/</loc>" in sitemap.text and 'hreflang="ar"' in sitemap.text and "xml" in sitemap.headers["content-type"]
    assert "getliyo" in client.get("/llms.txt").text


def test_custom_404_and_api_404(client):
    r = client.get("/yok-boyle-bir-sayfa")
    assert r.status_code == 404 and "404" in r.text
    assert client.get("/api/jobs/yok").status_code == 404 and client.get("/api/jobs/yok").json()["detail"]


def test_favicon_assets(client):
    for path in ("/favicon.svg", "/favicon.ico", "/apple-touch-icon.png"):
        assert client.get(path).status_code == 200, path


def test_gzip_and_cache_headers(client):
    r = client.get("/style.css", headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") == "gzip"
    assert r.headers["cache-control"] == "no-cache"  # js/css güncellemeleri hemen yansısın
    assert "max-age" in client.get("/favicon.svg").headers["cache-control"]
    assert client.get("/tr/").headers["cache-control"] == "no-cache"
    assert client.get("/tr/").headers["x-content-type-options"] == "nosniff"


def test_host_header_not_injected(tmp_path):
    cfg = Config(data_dir=tmp_path, download_dir=tmp_path / "dl", api_keys=frozenset(), secret=b"s" * 32)
    (tmp_path / "dl").mkdir()
    with TestClient(create_app(cfg, FakeManager())) as c:
        html = c.get("/tr/", headers={"Host": 'evil.com"><script>'}).text
        assert "evil.com" not in html


def test_context_menu_guard_on_all_pages(client):
    assert "contextmenu" in client.get("/guard.js").text
    for page in html_pages():
        assert "guard.js" in page.read_text(encoding="utf-8"), page.name


# ---------------------------------------------------------------- çok dillilik
from server import site as site_mod  # noqa: E402


@pytest.mark.parametrize("lang", ["tr", "en", "ar"])
def test_localized_home_and_legal(client, lang):
    home = client.get(f"/{lang}/")
    assert home.status_code == 200 and f'<html lang="{lang}" dir="{"rtl" if lang == "ar" else "ltr"}">' in home.text
    assert "{{" not in home.text
    for other in ("tr", "en", "ar"):
        assert f'hreflang="{other}" href="https://getliyo.example/{other}/"' in home.text
    assert 'hreflang="x-default"' in home.text and 'class="langs"' in home.text
    for slug in site_mod.LEGAL_SLUGS:
        r = client.get(f"/{lang}/{slug}")
        assert r.status_code == 200 and "{{" not in r.text and "<h1>" in r.text, (lang, slug)
        assert f'lang="{lang}"' in r.text


def test_all_locales_have_same_keys():
    import json
    keys = {l: set(json.loads((WEB_DIR / "locales" / f"{l}.json").read_text(encoding="utf-8"))) for l in ("tr", "en", "ar")}
    assert keys["tr"] == keys["en"] == keys["ar"]


def test_legacy_legal_redirects(client):
    r = client.get("/legal/gizlilik.html", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/tr/privacy"


@pytest.mark.parametrize("country,accept,cookie,expected", [
    ("TR", "en-US", "", "tr"), ("SA", "en", "", "ar"), ("EG", "", "", "ar"), ("DE", "en", "", "en"),
    ("DE", "tr-TR,tr;q=0.9", "", "tr"), ("", "ar-SA,ar;q=0.9", "", "ar"), ("", "fr", "", "en"),
    ("TR", "en", "ar", "ar"), ("US", "", "tr", "tr"), ("XX", "", "zz", "en"),
])
def test_root_redirect(client, country, accept, cookie, expected):
    headers = {"Accept-Language": accept} if accept else {}
    if country:
        headers["CF-IPCountry"] = country
    cookies = {"gl_lang": cookie} if cookie else {}
    r = client.get("/", headers=headers, cookies=cookies, follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == f"/{expected}/"
    assert "no-store" in r.headers["cache-control"]


def test_bots_are_never_redirected(client):
    for ua in ("Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)", "Bingbot/2.0", "facebookexternalhit/1.1"):
        r = client.get("/", headers={"User-Agent": ua, "CF-IPCountry": "TR"}, follow_redirects=False)
        assert r.status_code == 200 and 'lang="en"' in r.text, ua


def test_instagram_validation():
    from server import instagram
    ok = ["https://www.instagram.com/p/ABC123/", "https://instagram.com/reel/XyZ/", "https://www.instagram.com/tv/AbC/",
          "https://www.instagram.com/stories/someone/3141592653589793238/", "https://www.instagram.com/someone/reel/ABC/"]
    for url in ok:
        instagram.check(url)
    for url in ("https://www.instagram.com/someone/", "https://www.instagram.com/accounts/login/", "https://www.instagram.com/"):
        with pytest.raises(Exception) as err:
            instagram.check(url)
        assert getattr(err.value, "key", "") == "ig_invalid"
    instagram.check("https://example.com/whatever")  # Instagram dışı bağlantılara karışmaz
