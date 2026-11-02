"""İş kuyruğu: indirmeleri havuzda çalıştırır, durumları SQLite'ta saklar (yeniden başlatmaya dayanıklı)."""
from __future__ import annotations

import json
import secrets
import shutil
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from app.downloaders.base_downloader import DownloadControl, DownloadTask, MediaEntry, MediaFormat, MediaInfo, ProgressInfo
from app.downloaders.manager import DownloaderManager
from app.media.media_utils import pick_format
from app.utils.errors import CancelledError, SkippedError, UserError, error_key, friendly_message
from app.utils.filename import max_stem_length
from app.utils.logger import get_logger
from app.utils.name_template import render_template
from server.config import Config

log = get_logger("server.jobs")

QUEUED, RUNNING, DONE, FAILED, CANCELLED = "queued", "running", "done", "failed", "cancelled"
ACTIVE = (QUEUED, RUNNING)
PRESETS = ("best", "best_mp4", "h1080", "h720", "audio")


class QuotaError(Exception):
    """Anahtarın aynı anda çalışan/bekleyen iş sınırı doldu."""


@dataclass
class Job:
    id: str
    owner: str
    url: str
    title: str
    platform: str
    kind: str
    label: str  # "1080p · mp4" gibi kullanıcıya gösterilen format özeti
    status: str = QUEUED
    percent: Optional[float] = None
    speed: Optional[float] = None
    eta: Optional[float] = None
    error: str = ""
    error_code: str = ""  # arayüzde çevrilebilmesi için hata anahtarı
    file_name: str = ""
    file_path: str = ""
    file_size: Optional[int] = None
    created_at: float = 0.0
    finished_at: Optional[float] = None


class JobStore:
    """Jobs tablosu: her satır bir JSON. Tek bağlantı + kilit (iş yükü küçük)."""

    def __init__(self, path: Path) -> None:
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._db.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, data TEXT NOT NULL)")
            self._db.commit()

    def save(self, job: Job) -> None:
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO jobs (id, data) VALUES (?, ?)", (job.id, json.dumps(asdict(job))))
            self._db.commit()

    def delete(self, job_id: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            self._db.commit()

    def load_all(self) -> list[Job]:
        with self._lock:
            rows = self._db.execute("SELECT data FROM jobs").fetchall()
        jobs = []
        for (data,) in rows:
            try:
                jobs.append(Job(**json.loads(data)))
            except (TypeError, ValueError):
                log.warning("Bozuk iş kaydı atlandı")
        return jobs

    def close(self) -> None:
        with self._lock:
            self._db.close()


class JobManager:
    def __init__(self, config: Config, manager: DownloaderManager) -> None:
        self.config, self.manager = config, manager
        self.store = JobStore(config.db_path)
        self._pool = ThreadPoolExecutor(max_workers=config.max_concurrent, thread_name_prefix="dl")
        self._lock = threading.RLock()
        self._controls: dict[str, DownloadControl] = {}
        self._jobs: dict[str, Job] = {j.id: j for j in self.store.load_all()}
        self._stop = threading.Event()
        for job in self._jobs.values():  # sunucu kapanırken yarım kalanlar
            if job.status in ACTIVE:
                job.status, job.error, job.error_code, job.finished_at = FAILED, "Sunucu yeniden başlatıldı, indirme yarım kaldı.", "download_failed", time.time()
                self.store.save(job)
        self.purge_expired()
        threading.Thread(target=self._purge_loop, name="purge", daemon=True).start()

    # ------------------------------------------------------------------ sorgu
    def get(self, job_id: str, owner: str | None = None) -> Optional[Job]:
        with self._lock:
            job = self._jobs.get(job_id)
        if job and (owner is None or job.owner == owner):
            return job
        return None

    def list(self, owner: str) -> list[Job]:
        with self._lock:  # _forget aynı sözlükten siliyor: "dict changed size" olmasın
            jobs = [j for j in self._jobs.values() if j.owner == owner]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)

    def active_count(self, owner: str | None = None) -> int:
        with self._lock:
            return sum(1 for j in self._jobs.values() if j.status in ACTIVE and (owner is None or j.owner == owner))

    # ------------------------------------------------------------------ oluşturma
    def submit(
        self, owner: str, info: MediaInfo, *, preset: str = "best", entries: list[int] | None = None,
        format_id: str | None = None,
    ) -> list[Job]:
        if preset not in PRESETS:
            raise UserError("Geçersiz kalite ayarı.", "format")
        wanted = entries or ([info.requested_index] if info.requested_index else [e.index for e in info.entries])
        wanted = wanted[: self.config.max_entries_per_request]
        by_index = {e.index: e for e in info.entries}

        planned: list[tuple[MediaEntry, MediaFormat]] = []
        for idx in wanted:
            entry = by_index.get(idx)
            if entry is None:
                raise UserError(f"{idx}. öğe bulunamadı.", "format")
            if format_id:
                fmt = next((f for f in entry.formats if f.format_id == format_id), None)
            else:
                fmt = pick_format(entry, preset)
            if fmt is None:
                raise UserError.from_key("format")
            limit = self.config.max_filesize_mb * 1024 * 1024
            if limit and fmt.filesize and fmt.filesize > limit:
                raise UserError(f"Dosya sunucu sınırını aşıyor ({self.config.max_filesize_mb} MB).", "disk")
            planned.append((entry, fmt))

        with self._lock:
            if self.active_count() + len(planned) > self.config.max_active_total:
                raise QuotaError("Sunucu şu an çok yoğun. Biraz sonra tekrar dene.")
            if self.active_count(owner) + len(planned) > self.config.max_active_per_key:
                raise QuotaError(f"Aynı anda en fazla {self.config.max_active_per_key} indirme yapabilirsin.")
            return [self._enqueue(owner, info, entry, fmt) for entry, fmt in planned]

    def _enqueue(self, owner: str, info: MediaInfo, entry: MediaEntry, fmt: MediaFormat) -> Job:
        job_id = secrets.token_urlsafe(9)
        title = entry.title
        if info.is_gallery and (not title or title == info.title or title.startswith("Medya")):
            title = f"{info.title} - {entry.index:02d}"
        out_dir = self.config.download_dir / job_id
        base = render_template(
            "{title}", title=title, uploader=entry.uploader or info.uploader, platform=info.platform,
            media_id=entry.media_id, max_len=max_stem_length(out_dir),
        )
        task = DownloadTask(
            title=title, url=entry.url or info.source_url, fmt=fmt, out_dir=out_dir, base_name=base,
            conflict="new", playlist_index=entry.playlist_index, platform=info.platform,
            rate_limit_bps=int(self.config.rate_limit_mbps * 1_000_000), proxy_url=self.config.proxy_url,
        )
        label = " · ".join(x for x in (fmt.resolution, fmt.container) if x)
        job = Job(id=job_id, owner=owner, url=info.source_url, title=title, platform=info.platform,
                  kind=fmt.kind, label=label, created_at=time.time())
        self._jobs[job_id] = job
        self._controls[job_id] = DownloadControl()
        self.store.save(job)
        self._pool.submit(self._run, job, task)
        return job

    # ------------------------------------------------------------------ çalıştırma
    def _on_progress(self, job: Job, info: ProgressInfo) -> None:
        job.percent, job.speed, job.eta = info.percent, info.speed, info.eta

    def _run(self, job: Job, task: DownloadTask) -> None:
        control = self._controls.get(job.id)
        if control is None or control.is_set():
            self._finish(job, CANCELLED)
            return
        job.status = RUNNING
        self.store.save(job)
        try:
            path = self.manager.download(task, lambda info: self._on_progress(job, info), control)
            self._complete(job, path)
        except SkippedError as exc:
            self._complete(job, Path(exc.path))
        except CancelledError:
            self._finish(job, CANCELLED)
        except Exception as exc:  # noqa: BLE001 - iş hatası sunucuyu düşürmemeli
            log.exception("İndirme başarısız: %s", job.id)
            self._finish(job, FAILED, error=friendly_message(exc), error_code=error_key(exc))

    def _complete(self, job: Job, path: Path) -> None:
        job.file_path, job.file_name = str(path), path.name
        try:
            job.file_size = path.stat().st_size
        except OSError:
            job.file_size = None
        job.percent, job.speed, job.eta = 100.0, None, None
        self._finish(job, DONE)

    def _finish(self, job: Job, status: str, error: str = "", error_code: str = "") -> None:
        job.status, job.error, job.error_code, job.finished_at = status, error, error_code, time.time()
        if status != DONE:
            self._remove_files(job)
        self._controls.pop(job.id, None)
        self.store.save(job)

    # ------------------------------------------------------------------ iptal / silme
    def cancel_or_delete(self, job_id: str, owner: str) -> bool:
        job = self.get(job_id, owner)
        if job is None:
            return False
        if job.status in ACTIVE:
            control = self._controls.get(job_id)
            if control:
                control.stop(keep_partial=False)
            return True  # durum, indirme durunca CANCELLED olur
        self._forget(job)
        return True

    def _remove_files(self, job: Job) -> None:
        shutil.rmtree(self.config.download_dir / job.id, ignore_errors=True)

    def _forget(self, job: Job) -> None:
        self._remove_files(job)
        with self._lock:
            self._jobs.pop(job.id, None)
        self.store.delete(job.id)

    # ------------------------------------------------------------------ temizlik
    def purge_expired(self) -> int:
        cutoff = time.time() - self.config.retention_minutes * 60
        old = [j for j in list(self._jobs.values()) if j.status not in ACTIVE and (j.finished_at or j.created_at) < cutoff]
        for job in old:
            self._forget(job)
        return len(old)

    def _purge_loop(self) -> None:
        while not self._stop.wait(60):  # dakikada bir süresi dolanları sil (saklama üst sınırı 15 dk)
            try:
                self.purge_expired()
            except Exception:  # noqa: BLE001
                log.exception("Temizlik başarısız")

    def shutdown(self) -> None:
        self._stop.set()
        for control in list(self._controls.values()):
            control.stop(keep_partial=False)
        self._pool.shutdown(wait=False, cancel_futures=True)
        self.store.close()
