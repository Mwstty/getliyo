"""Çok dilli sayfa üretimi (TR/EN/AR): şablonlar + locales/*.json + yasal sayfa parçaları, dil seçimi."""
from __future__ import annotations

import html
import json
import re
from functools import lru_cache
from pathlib import Path

LANGS = ("tr", "en", "ar")
DEFAULT_LANG = "en"
RTL = frozenset({"ar"})
LANG_NAMES = {"tr": "Türkçe", "en": "English", "ar": "العربية"}
OG_LOCALE = {"tr": "tr_TR", "en": "en_US", "ar": "ar_AR"}
LEGAL_SLUGS = ("terms", "privacy", "copyright", "cookies", "contact")
LEGACY_LEGAL = {  # eski Türkçe adresler → yeni adresler (kalıcı yönlendirme)
    "/legal/kullanim-sartlari.html": "terms",
    "/legal/gizlilik.html": "privacy",
    "/legal/telif-bildirimi.html": "copyright",
}
LANG_COOKIE = "gl_lang"

TR_COUNTRY = frozenset({"TR"})
AR_COUNTRIES = frozenset(
    "SA AE EG QA KW BH OM JO IQ MA DZ TN LY LB SY YE SD PS MR".split()
)
BOT_RE = re.compile(
    r"bot|crawl|spider|slurp|mediapartners|facebookexternalhit|embedly|preview|"
    r"ia_archiver|semrush|ahrefs|yandex|baidu|duckduck|applebot|whatsapp|telegram",
    re.IGNORECASE,
)

ROOT = Path(__file__).parent
WEB_DIR = ROOT / "web"
TEMPLATES = ROOT / "templates"
PAGES = ROOT / "pages"
_TOKEN = re.compile(r"\{\{(t|h):([A-Za-z0-9_.]+)\}\}")


def is_bot(user_agent: str) -> bool:
    return bool(BOT_RE.search(user_agent or ""))


def _accept_language(header: str) -> str | None:
    """Accept-Language içinde ilk desteklenen dil (q değerine göre sıralı)."""
    ranked: list[tuple[float, int, str]] = []
    for i, part in enumerate((header or "").split(",")):
        bits = part.strip().split(";")
        tag = bits[0].strip().lower().split("-")[0]
        q = 1.0
        for b in bits[1:]:
            b = b.strip()
            if b.startswith("q="):
                try:
                    q = float(b[2:])
                except ValueError:
                    q = 0.0
        if tag in LANGS and q > 0:
            ranked.append((-q, i, tag))
    return min(ranked)[2] if ranked else None


def pick_lang(*, cookie: str = "", country: str = "", accept_language: str = "") -> str:
    """Sıra: kayıtlı seçim → ülke (TR/Arapça ülkeler) → Accept-Language → İngilizce."""
    if cookie in LANGS:
        return cookie
    country = (country or "").strip().upper()
    if country in TR_COUNTRY:
        return "tr"
    if country in AR_COUNTRIES:
        return "ar"
    return _accept_language(accept_language) or DEFAULT_LANG


@lru_cache(maxsize=None)
def _load_locale(lang: str, mtime: float) -> dict[str, str]:
    return json.loads((WEB_DIR / "locales" / f"{lang}.json").read_text(encoding="utf-8"))


def locale(lang: str) -> dict[str, str]:
    path = WEB_DIR / "locales" / f"{lang}.json"
    return _load_locale(lang, path.stat().st_mtime)


def _page_url(base: str, lang: str, slug: str) -> str:
    return f"{base}/{lang}/{slug}" if slug else f"{base}/{lang}/"


def hreflang_links(base: str, slug: str) -> str:
    links = [
        f'<link rel="alternate" hreflang="{lang}" href="{_page_url(base, lang, slug)}">' for lang in LANGS
    ]
    links.append(f'<link rel="alternate" hreflang="x-default" href="{base}/">')
    return "\n".join(links)


def lang_switch(slug: str, current: str, label: str) -> str:
    items = []
    for lang in LANGS:
        cur = ' aria-current="true"' if lang == current else ""
        items.append(
            f'<a href="/{lang}/{slug}" hreflang="{lang}" lang="{lang}" data-lang="{lang}"{cur}>{LANG_NAMES[lang]}</a>'
        )
    return f'<nav class="langs" aria-label="{html.escape(label)}">{"".join(items)}</nav>'


def _fill(text: str, strings: dict[str, str], fallback: dict[str, str]) -> str:
    def repl(m: re.Match) -> str:
        kind, key = m.group(1), m.group(2)
        value = strings.get(key, fallback.get(key, key))
        return html.escape(value, quote=True) if kind == "t" else value

    return _TOKEN.sub(repl, text)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def render_page(name: str, lang: str, base: str, slug: str = "", **extra: str) -> str:
    """templates/{name}.html dosyasını verilen dilde üretir."""
    strings, fallback = locale(lang), locale(DEFAULT_LANG)
    values = {
        "LANG": lang,
        "DIR": "rtl" if lang in RTL else "ltr",
        "OG_LOCALE": OG_LOCALE[lang],
        "SITE_URL": base,
        "CANONICAL": _page_url(base, lang, slug),
        "HREFLANG": hreflang_links(base, slug),
        "LANGSWITCH": lang_switch(slug, lang, strings.get("lang.label", "Language")),
        **extra,
    }
    text = _read(TEMPLATES / f"{name}.html")
    text = _fill(text, strings, fallback)
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def render_legal(lang: str, slug: str, base: str) -> str | None:
    """Yasal sayfa: pages/{lang}/{slug}.html parçasını ortak çerçeveye yerleştirir."""
    fragment = PAGES / lang / f"{slug}.html"
    meta_file = PAGES / lang / "meta.json"
    if slug not in LEGAL_SLUGS or not fragment.is_file() or not meta_file.is_file():
        return None
    meta = json.loads(_read(meta_file)).get(slug, {})
    return render_page(
        "legal", lang, base, slug,
        CONTENT=_read(fragment),
        PAGE_TITLE=html.escape(meta.get("title", slug), quote=True),
        PAGE_DESC=html.escape(meta.get("description", ""), quote=True),
    )


def render_result(lang: str, base: str, *, file_name: str = "", file_size: int | None = None,
                  download_url: str = "") -> str:
    """Instagram DM ile gönderilen sonuç sayfası. download_url boşsa "bağlantı geçersiz/süresi dolmuş" gösterilir."""
    strings, fallback = locale(lang), locale(DEFAULT_LANG)

    def t(key: str) -> str:
        return html.escape(strings.get(key, fallback.get(key, key)), quote=True)

    if download_url:
        size = f' <span class="muted">({file_size / 1_048_576:.1f} MB)</span>' if file_size else ""
        body = (
            f'<section class="card stack"><h1>{t("result.ready")}</h1>'
            f'<p>{html.escape(file_name)}{size}</p>'
            f'<p><a class="btn primary big" rel="nofollow" href="{html.escape(download_url, quote=True)}" download>'
            f'{t("result.download")}</a></p><p class="muted">{t("result.note")}</p></section>'
        )
    else:
        body = (
            f'<section class="card stack"><h1>{t("result.gone_title")}</h1><p>{t("result.gone_text")}</p>'
            f'<p><a class="btn" href="/{lang}/">{t("result.home")}</a></p></section>'
        )
    text = _fill(_read(TEMPLATES / "result.html"), strings, fallback)
    for key, value in {"LANG": lang, "DIR": "rtl" if lang in RTL else "ltr", "BODY": body}.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def sitemap_xml(base: str) -> str:
    rows = []
    slugs = ("",) + LEGAL_SLUGS
    for slug in slugs:
        alts = "".join(
            f'<xhtml:link rel="alternate" hreflang="{lang}" href="{_page_url(base, lang, slug)}"/>' for lang in LANGS
        )
        for lang in LANGS:
            prio, freq = ("1.0", "monthly") if not slug else ("0.3", "yearly")
            rows.append(
                f"  <url><loc>{_page_url(base, lang, slug)}</loc>{alts}"
                f"<changefreq>{freq}</changefreq><priority>{prio}</priority></url>"
            )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
        + "\n".join(rows) + "\n</urlset>\n"
    )
