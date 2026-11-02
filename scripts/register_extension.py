"""Chrome/Edge eklentisini Native Messaging host'una bağlar (Windows, HKCU -- yönetici gerekmez).

Bu dosya ayrıca kendi başına çalışan bir EXE olarak derlenir (kurulum sırasında
getliyo-host.exe ile aynı klasöre konur). Cift tiklayip Extension ID'yi
yapıştırman yeterli; ayrı bir Python/venv kurulumuna ihtiyaç yoktur.

Konsol cikti mesajlari kasitli olarak sadece ASCII: derlenmis EXE bir konsol penceresi
actiginda Turkce ozel karakterler (i, s, g, o, u, c) yanlis kod sayfasinda bozuk
gorunebiliyor; bu yuzden mesajlar duz ASCII tutuluyor.
"""
from __future__ import annotations

import json
import os
import sys
import winreg
from pathlib import Path

HOST_NAME = "com.getliyo.app"
HOST_EXE_NAME = "getliyo-host.exe"
SCRIPT_DIR = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR if getattr(sys, "frozen", False) else SCRIPT_DIR.parent

# Registry hive'lari: ikisi de ayni manifest dosyasini gosterebilir (Chromium tabanli).
REGISTRY_HIVES = [
    r"Software\Google\Chrome\NativeMessagingHosts",
    r"Software\Microsoft\Edge\NativeMessagingHosts",
]


def find_host_exe() -> Path | None:
    """Derlenmis host EXE'sini olasi konumlarda arar."""
    candidates = [
        SCRIPT_DIR / HOST_EXE_NAME,  # kurulu uygulamada: bu arac ile ayni klasorde
        PROJECT_ROOT / "dist" / HOST_EXE_NAME,  # gelistirme: scripts\build.bat sonrasi
    ]
    for base_env in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(base_env)
        if base:
            candidates.append(Path(base) / "getliyo" / HOST_EXE_NAME)
    for c in candidates:
        if c.is_file():
            return c
    return None


def write_manifest(host_exe: Path, extension_id: str) -> Path:
    manifest = {
        "name": HOST_NAME,
        "description": "getliyo - tarayicidan baglanti gonderme koprusu",
        "path": str(host_exe),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{extension_id}/"],
    }
    out_dir = Path.home() / "AppData" / "Local" / "getliyo"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "native-messaging-host.json"
    out_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def register(manifest_path: Path) -> None:
    for hive_path in REGISTRY_HIVES:
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"{hive_path}\\{HOST_NAME}")
        winreg.SetValue(key, "", winreg.REG_SZ, str(manifest_path))
        winreg.CloseKey(key)


def main() -> int:
    print("=== getliyo - Tarayici Eklentisi Kayit Araci ===\n")

    if sys.platform != "win32":
        print("Bu arac yalnizca Windows'ta calisir.")
        return 1

    host_exe = find_host_exe()
    if not host_exe:
        print(
            "[HATA] getliyo-host.exe bulunamadi.\n"
            "Bu araci getliyo'nin kurulu oldugu klasorden calistirdigindan emin ol."
        )
        return 1
    print(f"Host EXE bulundu: {host_exe}\n")

    ext_id = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
    if not ext_id:
        print("Once su adimlari yap:")
        print("  1) Chrome'da adres cubuguna 'chrome://extensions' yaz, Enter'a bas.")
        print("  2) Sag ustten 'Gelistirici modu' anahtarini ac.")
        print("  3) 'Paketlenmemis oge yukle' butonuna bas, 'browser-extension' klasorunu sec.")
        print("  4) Eklenti kartinin altinda goreceginn 32 karakterlik ID'yi kopyala.\n")
        ext_id = input("Extension ID'yi buraya yapistir ve Enter'a bas: ").strip()
    if len(ext_id) != 32 or not ext_id.isalnum():
        print("\n[HATA] Gecersiz Extension ID (32 harften olusmali).")
        input("\nCikmak icin Enter'a bas...")
        return 1

    manifest_path = write_manifest(host_exe, ext_id)
    register(manifest_path)
    print(f"\nKayit tamam.\n  Manifest : {manifest_path}\n  Host     : {host_exe}")
    print("\nSimdi Chrome'u tamamen kapatip yeniden ac, sonra eklentiyi dene.")
    input("\nCikmak icin Enter'a bas...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
