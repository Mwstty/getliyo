"""Instagram mention -> otomatik indirme bağlantısı (AŞAMA 6, yalnızca Meta'nın resmi belgelediği akış).

Akış:
1. Kullanıcı Getliyo'nun Instagram hesabını bir gönderi/reel altında yorumla etiketler (mention).
2. Meta, `mentions` webhook alanını bu modülün POST uç noktasına gönderir.
3. `GET /<IG_ID>/tags` ile yorumun bağlı olduğu medyanın herkese açık adresi (permalink) çözülür.
4. Mevcut indirme motoru (DownloaderManager/JobStore) tetiklenir, imzalı bağlantı üretilir.
5. Private Reply (`POST /<IG_ID>/messages`, aynı comment_id) ile yoruma DM gönderilir.

Meta'nın belgelediği, aşılmayan sınırlar:
- Stories mention desteklenmez (webhook hiç gelmez).
- Özel (private) hesaplardan gelen etiketlemede webhook tetiklenmez.
- Bir yorum için en fazla BİR private reply gönderilebilir, oluşturulmasından 7 gün içinde.
Bu modül bu sınırları aşmaya çalışmaz; aşağıdaki kod yalnızca bu resmi akışı uygular.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Callable, Optional

import httpx

from app.utils.errors import UserError
from app.utils.logger import get_logger

log = get_logger("server.social.instagram")

GRAPH_API = "https://graph.facebook.com/v21.0"
POLL_INTERVAL_S = 3.0
POLL_TIMEOUT_S = 600.0  # 10 dk — bu sürede bitmeyen iş için kullanıcıya "gecikme" mesajı gönderilir


def verify_signature(app_secret: str, body: bytes, signature_header: str | None) -> bool:
    """Meta'nın `X-Hub-Signature-256` başlığını doğrular (HMAC-SHA256, App Secret ile)."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    got = signature_header[len("sha256="):]
    return hmac.compare_digest(expected, got)


def verify_subscription(verify_token: str, mode: str | None, token: str | None, challenge: str | None) -> str | None:
    """Webhook kurulum adımı (Meta'nın GET isteği): doğru token gelirse challenge aynen döndürülür."""
    if mode == "subscribe" and token and verify_token and hmac.compare_digest(token, verify_token):
        return challenge
    return None


@dataclass
class MentionEvent:
    ig_id: str
    comment_id: str
    raw: dict


def extract_mentions(payload: dict) -> list[MentionEvent]:
    """Webhook gövdesinden `mentions` alanındaki olayları çıkarır. Başka alanları (ör. `comments`) yok sayar."""
    out: list[MentionEvent] = []
    for entry in payload.get("entry", []):
        ig_id = entry.get("id", "")
        for change in entry.get("changes", []):
            if change.get("field") != "mentions":
                continue
            value = change.get("value") or {}
            comment_id = value.get("comment_id")
            if comment_id:
                out.append(MentionEvent(ig_id=ig_id, comment_id=comment_id, raw=value))
    return out


class InstagramClient:
    """Graph API ağ çağrıları (tag/medya sorgusu, private reply gönderimi) — testlerde sahteleştirilir."""

    def __init__(self, page_token: str, business_id: str, timeout: float = 10.0) -> None:
        self.page_token = page_token
        self.business_id = business_id
        self.timeout = timeout

    def resolve_tagged_media_url(self, comment_id: str) -> Optional[str]:
        """Yorumun bağlı olduğu medyanın herkese açık permalink'ini döndürür (bulunamazsa None)."""
        try:
            r = httpx.get(
                f"{GRAPH_API}/{self.business_id}/tags",
                params={"access_token": self.page_token, "fields": "id,media_url,permalink,caption"},
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json().get("data", [])
        except Exception:
            log.exception("Instagram tags sorgusu başarısız (comment_id=%s)", comment_id)
            return None
        for item in data:
            if item.get("id") == comment_id:
                return item.get("permalink") or item.get("media_url")
        return None

    def send_private_reply(self, comment_id: str, text: str) -> bool:
        """Yorum başına TEK SEFER çalışır (Meta kuralı); ikinci çağrı reddedilir, bu beklenen bir durumdur."""
        try:
            r = httpx.post(
                f"{GRAPH_API}/{self.business_id}/messages",
                params={"access_token": self.page_token},
                json={"recipient": {"comment_id": comment_id}, "message": {"text": text}},
                timeout=self.timeout,
            )
            ok = r.status_code < 300
            if not ok:
                log.warning("Private reply reddedildi (comment_id=%s): %s", comment_id, r.text[:300])
            return ok
        except Exception:
            log.exception("Private reply gönderilemedi (comment_id=%s)", comment_id)
            return False


def process_mention(
    event: MentionEvent,
    client: InstagramClient,
    *,
    analyze: Callable[[str], object],
    submit: Callable[[str, object], list],
    get_job: Callable[[str], object],
    build_download_link: Callable[[str], str],
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> None:
    """Tek bir mention olayını uçtan uca işler. Dışa açık fonksiyonlardan sızan bir istisna
    bu çağrıyı durdurmaz; her adım kendi içinde hatayı loglayıp nazik bir DM ile kapanır."""
    media_url = client.resolve_tagged_media_url(event.comment_id)
    if not media_url:
        log.info("Mention için medya çözülemedi (comment_id=%s) — yanıt gönderilmiyor.", event.comment_id)
        return

    owner = f"instagram:{event.ig_id}"
    try:
        info = analyze(media_url)
        created = submit(owner, info)
    except UserError as exc:
        client.send_private_reply(event.comment_id, f"Bu içeriği indiremedim: {exc}")
        return
    except Exception:
        log.exception("Mention indirme tetikleme başarısız (comment_id=%s)", event.comment_id)
        client.send_private_reply(event.comment_id, "Bir hata oluştu, lütfen getliyo.com üzerinden dene.")
        return

    if not created:
        client.send_private_reply(event.comment_id, "Bu içerik için indirilebilir bir dosya bulunamadı.")
        return

    job = created[0]
    deadline = now() + POLL_TIMEOUT_S
    while now() < deadline:
        job = get_job(job.id)
        if job is None:
            client.send_private_reply(event.comment_id, "İşlem bulunamadı, lütfen tekrar etiketleyin.")
            return
        if job.status == "done":
            link = build_download_link(job.id)
            client.send_private_reply(event.comment_id, f"İşte indirme bağlantın: {link}")
            return
        if job.status in ("failed", "cancelled"):
            client.send_private_reply(event.comment_id, "İndirme başarısız oldu, lütfen getliyo.com üzerinden dene.")
            return
        sleep(POLL_INTERVAL_S)

    client.send_private_reply(event.comment_id, "İşlem beklenenden uzun sürdü, getliyo.com üzerinden takip edebilirsin.")
