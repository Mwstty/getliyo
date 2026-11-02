"""Instagram DM -> indirme -> sonuç bağlantısı (yalnızca Meta'nın resmî Instagram Messaging API'si).

Akış:
1. Kullanıcı Getliyo'nun profesyonel hesabına herkese açık bir video bağlantısı yollar.
2. Meta, `messages` webhook alanını `/webhooks/instagram` adresine POST eder (imza app.py'de doğrulanır).
3. Mesajdaki TEK bağlantı ayıklanır, mevcut indirme motoru (JobManager) ile işe alınır.
4. İş bitince, Send API ile AYNI konuşmaya `/r/<token>` sonuç sayfasının süreli bağlantısı yazılır.

Sınırlar: yalnızca kullanıcının başlattığı konuşmaya yanıt verilir (Meta'nın 24 saatlik mesajlaşma penceresi);
yanıt reddedilirse başka yol denenmez, yalnızca loglanır. Dosya eki gönderilmez; saklama süresi mevcut
`retention_minutes` kuralıdır.
"""
from __future__ import annotations

import hashlib
import hmac
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import httpx

from app.utils.errors import UserError
from app.utils.logger import get_logger
from app.utils.url_extract import parse_urls
from server.jobs import ACTIVE, DONE, QuotaError
from server.social.instagram import GRAPH_API

log = get_logger("server.social.instagram_dm")

POLL_INTERVAL_S = 3.0
PROCESSING_NOTICE_AFTER_S = 20.0  # bu süreyi aşan işlerde BİR kez "işleniyor" yazılır
GIVE_UP_AFTER_S = 600.0
SEEN_TTL_S = 24 * 3600  # Meta aynı olayı yeniden gönderebilir; bu süre içinde tekrar işlenmez
MAX_TEXT = 1000  # Send API metin sınırının altında kal

MSG_NO_LINK = "Merhaba! İndirmek istediğin herkese açık videonun bağlantısını (YouTube, TikTok, Instagram, Facebook, Reddit…) bana yaz."
MSG_MANY_LINKS = "Mesajında birden fazla bağlantı var. Lütfen her seferinde yalnızca tek bir bağlantı gönder."
MSG_UNSUPPORTED = "Bu bağlantıyı indiremedim. Herkese açık bir video bağlantısı olduğundan emin olup tekrar dene."
MSG_BUSY = "Şu an çok yoğunum. Biraz sonra tekrar dener misin?"
MSG_PROCESSING = "İndirme hazırlanıyor, biraz sürebilir. Hazır olunca bağlantıyı buraya göndereceğim."
MSG_FAILED = "İndirme başarısız oldu. Bağlantının herkese açık olduğundan emin olup tekrar dene."
MSG_TIMEOUT = "İşlem beklenenden uzun sürdü ve tamamlanamadı. Daha sonra tekrar dene."
MSG_ERROR = "Bir sorun oluştu. Lütfen biraz sonra tekrar dene."


def result_token(secret: bytes, job_id: str, expires: int) -> str:
    """`<iş>.<bitiş>.<imza>`: tahmin edilemez (iş kimliği rastgele + HMAC) ve süreli."""
    sig = hmac.new(secret, f"result.{job_id}.{expires}".encode(), hashlib.sha256).hexdigest()
    return f"{job_id}.{expires}.{sig}"


def parse_result_token(secret: bytes, token: str, now: float | None = None) -> Optional[str]:
    """Geçerli ve süresi dolmamış belirteçte iş kimliğini döndürür, aksi halde None."""
    parts = (token or "").split(".")
    if len(parts) != 3 or not parts[1].isdigit():
        return None
    job_id, expires, sig = parts[0], int(parts[1]), parts[2]
    expected = hmac.new(secret, f"result.{job_id}.{expires}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    if expires < (now if now is not None else time.time()):
        return None
    return job_id


@dataclass(frozen=True)
class DmEvent:
    sender_id: str
    message_id: str
    text: str


def extract_messages(payload: dict) -> list[DmEvent]:
    """Webhook gövdesinden kullanıcı mesajlarını çıkarır; echo (kendi mesajlarımız), okundu/tepki olayları
    ve kendi hesabımızdan gelenler yok sayılır."""
    out: list[DmEvent] = []
    if payload.get("object") != "instagram":
        return out
    for entry in payload.get("entry", []):
        own_id = str(entry.get("id", ""))
        for item in entry.get("messaging", []) or []:
            msg = item.get("message")
            sender = str((item.get("sender") or {}).get("id", ""))
            if not isinstance(msg, dict) or msg.get("is_echo") or not sender or sender == own_id:
                continue
            mid, text = msg.get("mid"), msg.get("text")
            if isinstance(mid, str) and mid:
                out.append(DmEvent(sender_id=sender, message_id=mid, text=text if isinstance(text, str) else ""))
    return out


class DmStore:
    """Yinelenen olay kaydı + bekleyen iş <-> konuşma eşlemesi (SQLite). Kişisel veri olarak yalnızca
    gönderen kimliği tutulur ve yanıt gönderilince (ya da zaman aşımında) silinir."""

    def __init__(self, path: Path) -> None:
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._db.execute("CREATE TABLE IF NOT EXISTS seen (mid TEXT PRIMARY KEY, ts REAL NOT NULL)")
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS pending (job_id TEXT PRIMARY KEY, sender TEXT NOT NULL, "
                "started REAL NOT NULL, notified INTEGER NOT NULL DEFAULT 0)"
            )
            self._db.commit()

    def first_time(self, mid: str) -> bool:
        """Olay ilk kez görülüyorsa kaydeder ve True döner (atomik)."""
        now = time.time()
        with self._lock:
            self._db.execute("DELETE FROM seen WHERE ts < ?", (now - SEEN_TTL_S,))
            cur = self._db.execute("INSERT OR IGNORE INTO seen (mid, ts) VALUES (?, ?)", (mid, now))
            self._db.commit()
            return cur.rowcount == 1

    def add_pending(self, job_id: str, sender: str) -> None:
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO pending (job_id, sender, started, notified) VALUES (?, ?, ?, 0)",
                             (job_id, sender, time.time()))
            self._db.commit()

    def pending(self) -> list[tuple[str, str, float, bool]]:
        with self._lock:
            rows = self._db.execute("SELECT job_id, sender, started, notified FROM pending").fetchall()
        return [(j, s, t, bool(n)) for j, s, t, n in rows]

    def mark_notified(self, job_id: str) -> None:
        with self._lock:
            self._db.execute("UPDATE pending SET notified = 1 WHERE job_id = ?", (job_id,))
            self._db.commit()

    def remove_pending(self, job_id: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM pending WHERE job_id = ?", (job_id,))
            self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()


class DmClient:
    """Send API çağrısı — testlerde sahteleştirilir. Token yalnızca isteğin parametresinde, loglara yazılmaz."""

    def __init__(self, page_token: str, business_id: str, timeout: float = 10.0) -> None:
        self.page_token, self.business_id, self.timeout = page_token, business_id, timeout

    def send_text(self, recipient_id: str, text: str) -> bool:
        try:
            r = httpx.post(
                f"{GRAPH_API}/{self.business_id}/messages",
                params={"access_token": self.page_token},
                json={"recipient": {"id": recipient_id}, "message": {"text": text[:MAX_TEXT]}},
                timeout=self.timeout,
            )
            if r.status_code >= 300:
                log.warning("DM gönderilemedi (HTTP %s)", r.status_code)  # yanıt gövdesi/kimlik loglanmaz
                return False
            return True
        except Exception:  # noqa: BLE001 - ağ hatası webhook akışını düşürmemeli
            log.warning("DM gönderilemedi (ağ hatası)")
            return False


class DmService:
    """DM olaylarını işe çevirir ve biten işlerin sonucunu geri yazar. Bağımlılıklar dışarıdan verilir;
    böylece indirme motoru ve Meta çağrıları testlerde değiştirilebilir."""

    def __init__(
        self, *, client, store: DmStore,
        check_url: Callable[[str], str], analyze: Callable[[str], object],
        submit: Callable[[str, object], list], get_job: Callable[[str], object],
        owner_for: Callable[[str], str], make_link: Callable[[object], str],
        allow: Callable[[str], bool] = lambda _s: True,
    ) -> None:
        self.client, self.store = client, store
        self._check_url, self._analyze, self._submit, self._get_job = check_url, analyze, submit, get_job
        self._owner_for, self._make_link, self._allow = owner_for, make_link, allow
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------ olay
    def accept(self, event: DmEvent) -> bool:
        """Webhook isteği içinde çağrılır (hızlı): olay yeniyse True. Yinelenen olay işe dönüşmez."""
        return self.store.first_time(event.message_id)

    def handle(self, event: DmEvent) -> None:
        """Tek mesajı işler (arka plan iş parçacığında). Hiçbir istisna dışarı sızmaz."""
        try:
            self._handle(event)
        except Exception:  # noqa: BLE001
            log.exception("DM işlenemedi")
            self.client.send_text(event.sender_id, MSG_ERROR)

    def _handle(self, event: DmEvent) -> None:
        if not self._allow(event.sender_id):
            log.info("DM hız sınırı aşıldı, yanıt verilmiyor")
            return
        urls = parse_urls(event.text)
        if not urls:
            self.client.send_text(event.sender_id, MSG_NO_LINK)
            return
        if len(urls) > 1:
            self.client.send_text(event.sender_id, MSG_MANY_LINKS)
            return
        try:
            url = self._check_url(urls[0])  # doğrulama + engelli alan + SSRF denetimi (mevcut kurallar)
            info = self._analyze(url)
            created = self._submit(self._owner_for(event.sender_id), info)
        except QuotaError:
            self.client.send_text(event.sender_id, MSG_BUSY)
            return
        except UserError as exc:
            # UserError iletileri kullanıcıya yönelik güvenli metinlerdir (dahili ayrıntı içermez).
            self.client.send_text(event.sender_id, f"{MSG_UNSUPPORTED} ({exc})" if str(exc) else MSG_UNSUPPORTED)
            return
        except Exception:  # noqa: BLE001
            log.exception("DM indirme tetikleme başarısız")
            self.client.send_text(event.sender_id, MSG_UNSUPPORTED)
            return
        if not created:
            self.client.send_text(event.sender_id, MSG_UNSUPPORTED)
            return
        self.store.add_pending(created[0].id, event.sender_id)  # çoklu öğede ilki; sonuç sayfası tek dosya sunar

    # ------------------------------------------------------------------ izleme
    def poll_once(self) -> None:
        """Bekleyen işleri kontrol eder; biten/başarısız/zaman aşımına uğrayanı yanıtlar ve kaydı siler."""
        for job_id, sender, started, notified in self.store.pending():
            job = self._get_job(job_id)
            age = time.time() - started
            if job is None:
                self.client.send_text(sender, MSG_ERROR)
            elif job.status == DONE:
                self.client.send_text(sender, f"Hazır! İndirme sayfan (kısa süre geçerli): {self._make_link(job)}")
            elif job.status in ACTIVE:
                if age > GIVE_UP_AFTER_S:
                    self.client.send_text(sender, MSG_TIMEOUT)
                elif age > PROCESSING_NOTICE_AFTER_S and not notified:
                    self.store.mark_notified(job_id)
                    self.client.send_text(sender, MSG_PROCESSING)
                    continue
                else:
                    continue
            else:
                self.client.send_text(sender, MSG_FAILED)  # hata ayrıntısı DM'e yazılmaz
            self.store.remove_pending(job_id)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="ig-dm", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.wait(POLL_INTERVAL_S):
            try:
                self.poll_once()
            except Exception:  # noqa: BLE001
                log.exception("DM izleyici hatası")

    def stop(self) -> None:
        self._stop.set()
        self.store.close()
