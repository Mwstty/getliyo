"""Sunucu yapılandırması: tamamen ortam değişkenleri (GETLIYO_*) ile, Docker/systemd dostu."""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: https:; "
    "connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default) or default)
    except ValueError:
        return default


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Config:
    data_dir: Path
    download_dir: Path
    api_keys: frozenset[str]  # boş = anahtarsız (yerel) mod
    secret: bytes  # indirme bağlantılarını imzalamak için
    max_concurrent: int = 2  # aynı anda çalışan indirme sayısı
    max_active_per_key: int = 5  # bir anahtarın bekleyen+çalışan iş sınırı
    max_active_total: int = 20  # tüm ziyaretçiler için toplam bekleyen+çalışan iş (aşırı yüklenmeye karşı)
    max_entries_per_request: int = 25  # playlist/galeri tek istekte en fazla kaç öğe
    retention_minutes: int = 15  # biten dosyalar ve kayıtlar bu süre sonra silinir (üst sınır 15)
    max_filesize_mb: int = 0  # 0 = sınırsız; VPS diskini korumak için önerilir
    analyze_per_minute: int = 30  # anahtar başına analiz sınırı
    rate_limit_mbps: float = 0.0  # 0 = sınırsız
    proxy_url: str = ""
    cors_origins: tuple[str, ...] = ()
    site_url: str = ""  # canonical/sitemap/paylaşım adresleri için, ör. https://getliyo.com (boşsa istekten türetilir)
    blocked_domains: tuple[str, ...] = ()  # telif bildirimi sonrası engellenen alan adları
    enable_docs: bool = False  # /api/docs ve openapi.json; üretimde kapalı kalmalı
    csp: str = DEFAULT_CSP  # reklam/analytics ağı kullanılacaksa GETLIYO_CSP ile genişletilmeli
    log_retention_days: int = 30  # erişim kaydı (IP, zaman, sayfa) saklama süresi; hukuki gereklilikle uyumlu belirle
    allow_private_urls: bool = False  # SADECE test için; açıkken SSRF koruması kapanır

    # --- Instagram mention -> otomatik indirme bağlantısı (AŞAMA 6) ---
    # Hepsi boşsa webhook endpoint'i 404 döner (özellik tamamen kapalı, varsayılan güvenli).
    instagram_app_secret: str = ""  # Meta App Dashboard -> App Secret (webhook imza doğrulama, X-Hub-Signature-256)
    instagram_verify_token: str = ""  # webhook kurulumunda Meta'ya girilen rastgele dize (GET doğrulama)
    instagram_page_token: str = ""  # Page access token (Graph API çağrıları + private reply göndermek için)
    instagram_business_id: str = ""  # IG Business/Creator hesabının Instagram-scoped ID'si
    public_base_url: str = ""  # DM'e yazılan sonuç bağlantılarının kökü, ör. https://getliyo.com (boşsa site_url)

    @property
    def auth_required(self) -> bool:
        return bool(self.api_keys)

    @property
    def instagram_enabled(self) -> bool:
        return bool(self.instagram_app_secret and self.instagram_verify_token
                    and self.instagram_page_token and self.instagram_business_id)

    @property
    def result_base_url(self) -> str:
        """DM'deki sonuç bağlantısının kökü. Boşsa DM gönderilmez (göreli bağlantı kullanıcıya işe yaramaz)."""
        return self.public_base_url or self.site_url

    @property
    def db_path(self) -> Path:
        return self.data_dir / "jobs.db"

    @classmethod
    def local(cls, data_dir: Path, download_dir: Path, max_concurrent: int = 2) -> "Config":
        """Masaüstü uygulamasının gömülü sunucusu: anahtarsız, yalnızca bu bilgisayardan erişilir."""
        data_dir.mkdir(parents=True, exist_ok=True)
        download_dir.mkdir(parents=True, exist_ok=True)
        secret_file = data_dir / "secret.key"
        if not secret_file.exists():
            secret_file.write_bytes(secrets.token_bytes(32))
        return cls(data_dir=data_dir, download_dir=download_dir, api_keys=frozenset(),
                   secret=secret_file.read_bytes(), max_concurrent=max_concurrent)

    @classmethod
    def from_env(cls) -> "Config":
        data_dir = Path(os.environ.get("GETLIYO_DATA_DIR", "server-data")).resolve()
        data_dir.mkdir(parents=True, exist_ok=True)
        download_dir = Path(os.environ.get("GETLIYO_DOWNLOAD_DIR", str(data_dir / "downloads"))).resolve()
        download_dir.mkdir(parents=True, exist_ok=True)

        # Boşsa kimlik doğrulama KAPALI (yerel kullanım). İnternete açarken mutlaka anahtar tanımla.
        keys = {k.strip() for k in os.environ.get("GETLIYO_API_KEYS", "").split(",") if k.strip()}

        secret_file = data_dir / "secret.key"
        if not secret_file.exists():
            secret_file.write_bytes(secrets.token_bytes(32))

        return cls(
            data_dir=data_dir,
            download_dir=download_dir,
            api_keys=frozenset(keys),
            secret=secret_file.read_bytes(),
            max_concurrent=max(1, _int("GETLIYO_MAX_CONCURRENT", 2)),
            max_active_per_key=max(1, _int("GETLIYO_MAX_ACTIVE_PER_KEY", 5)),
            max_entries_per_request=max(1, _int("GETLIYO_MAX_ENTRIES", 25)),
            retention_minutes=min(15, max(5, _int("GETLIYO_RETENTION_MINUTES", 15))),
            max_filesize_mb=max(0, _int("GETLIYO_MAX_FILESIZE_MB", 2000)),
            analyze_per_minute=max(1, _int("GETLIYO_ANALYZE_PER_MINUTE", 30)),
            rate_limit_mbps=_float("GETLIYO_RATE_LIMIT_MBPS", 0.0),
            proxy_url=os.environ.get("GETLIYO_PROXY_URL", "").strip(),
            cors_origins=tuple(o.strip() for o in os.environ.get("GETLIYO_CORS_ORIGINS", "").split(",") if o.strip()),
            site_url=os.environ.get("GETLIYO_SITE_URL", "").strip().rstrip("/"),
            blocked_domains=tuple(d.strip().lower().lstrip(".") for d in os.environ.get("GETLIYO_BLOCKED_DOMAINS", "").split(",") if d.strip()),
            max_active_total=max(1, _int("GETLIYO_MAX_ACTIVE_TOTAL", 20)),
            enable_docs=_flag("GETLIYO_ENABLE_DOCS"),
            csp=os.environ.get("GETLIYO_CSP", "").strip() or DEFAULT_CSP,
            log_retention_days=max(1, _int("GETLIYO_LOG_RETENTION_DAYS", 30)),
            allow_private_urls=_flag("GETLIYO_ALLOW_PRIVATE_URLS"),
            instagram_app_secret=os.environ.get("GETLIYO_IG_APP_SECRET", "").strip(),
            instagram_verify_token=os.environ.get("GETLIYO_IG_VERIFY_TOKEN", "").strip(),
            instagram_page_token=os.environ.get("GETLIYO_IG_PAGE_TOKEN", "").strip(),
            instagram_business_id=os.environ.get("GETLIYO_IG_BUSINESS_ID", "").strip(),
            public_base_url=os.environ.get("GETLIYO_PUBLIC_BASE_URL", "").strip().rstrip("/"),
        )
