"""Üretim derlemesi öncesi kaynak kodu karartma: app/ ve server/ -> build/obfuscated/.

PyArmor ile Python bayt kodu şifrelenir (gerçek kaynak hiçbir yerde düz metin kalmaz,
yalnızca `pyarmor_runtime_*` eşliğinde çalışır). PyInstaller daha sonra bu karartılmış
kopyayı paketler (build/getliyo.spec zaten build/obfuscated/ üzerinden okuyacak şekilde
ayarlı).

Not: PyArmor'un deneme sürümü tek dosyada belirli bir büyüklüğü aşınca ("out of license")
başarısız oluyor — bu proje için yalnızca app/ui/main_window.py bu sınıra takılıyor, o
dosya karartılmadan (kaynak haliyle) kopyalanır; geri kalan ~70 dosya karartılır.
Ücretli PyArmor lisansı alınırsa EXCLUDE listesi boşaltılabilir.

Kullanım:  scripts\\build.bat  (otomatik çağırır)
       ya da:  .venv\\Scripts\\python.exe scripts\\build_obfuscate.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build" / "obfuscated"
PYARMOR = ROOT / ".venv" / "Scripts" / "pyarmor.exe"

# PyArmor trial lisansı bu dosyada "out of license" veriyor (tek dosya boyut sınırı).
EXCLUDE = ["app/ui/main_window.py"]


def main() -> int:
    if not PYARMOR.exists():
        print("PyArmor bulunamadı: .venv içine 'pip install pyarmor' gerekiyor.", file=sys.stderr)
        return 1

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    cmd = [str(PYARMOR), "gen", "-O", str(OUT), "-r"]
    for pattern in EXCLUDE:
        cmd += ["--exclude", pattern]
    cmd += ["app", "server"]
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)

    # Karartılmadan bırakılan dosyaları (EXCLUDE) kaynaktan olduğu gibi kopyala.
    for rel in EXCLUDE:
        src = ROOT / rel
        dst = OUT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"[bilgi] {rel} karartılmadan kopyalandı (PyArmor trial sınırı).")

    runtime_dirs = list(OUT.glob("pyarmor_runtime_*"))
    if not runtime_dirs:
        print("[HATA] pyarmor_runtime_* klasörü üretilmedi.", file=sys.stderr)
        return 1

    print(f"Hazır: {OUT.relative_to(ROOT)}  (çalışma zamanı: {runtime_dirs[0].name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
