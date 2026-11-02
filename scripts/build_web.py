"""Üretim web paketi: server/web -> server/web-dist (JS küçültülür/karartılır, kaynak harita üretilmez).

Gereksinim: Node.js (npx). Araçlar sürümü sabitlenmiş olarak gerektiğinde indirilir; projeye node_modules eklenmez.
Kullanım:  python scripts/build_web.py

Not: Karartma gizli bilgiyi korumaz; web kodunda hiçbir anahtar/parola bulunmamalıdır (bu betik bunu da denetler).
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "server" / "web"
DST = ROOT / "server" / "web-dist"

TERSER = "terser@5.36.0"
OBFUSCATOR = "javascript-obfuscator@4.1.1"
# Site sahibinin düzenlediği dosyalar: yalnızca küçültülür, karartılmaz.
MINIFY_ONLY = {"site-config.js", "ads.js"}
SECRET_PATTERN = re.compile(r"(?i)(api[_-]?key|secret|token|passw(or)?d)\s*[:=]\s*['\"][^'\"]{8,}")

_NPX = shutil.which("npx") or shutil.which("npx.cmd") or "npx"


def _npx(*args: str) -> None:
    subprocess.run([_NPX, "--yes", *args], check=True)


def _minify_css(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"\s+", " ", text)
    return re.sub(r"\s*([{};:,>])\s*", r"\1", text).replace(";}", "}").strip()


def main() -> int:
    if not SRC.is_dir():
        print("server/web bulunamadı", file=sys.stderr)
        return 1
    if DST.exists():
        shutil.rmtree(DST)
    shutil.copytree(SRC, DST)

    for js in sorted(DST.glob("*.js")):
        if SECRET_PATTERN.search(js.read_text(encoding="utf-8")):
            print(f"[UYARI] {js.name} içinde gizli bilgiye benzeyen bir değer var — yayından önce kaldırın.", file=sys.stderr)
        tmp = js.with_name(js.stem + ".__min.js")
        _npx(TERSER, str(js), "--compress", "--mangle", "--output", str(tmp))
        if js.name in MINIFY_ONLY:
            tmp.replace(js)
            continue
        _npx(OBFUSCATOR, str(tmp), "--output", str(js), "--compact", "true", "--string-array", "true",
             "--string-array-encoding", "base64", "--string-array-threshold", "0.75", "--rename-globals", "false",
             "--identifier-names-generator", "hexadecimal", "--source-map", "false", "--self-defending", "false")
        tmp.unlink()

    css = DST / "style.css"
    if css.exists():
        css.write_text(_minify_css(css.read_text(encoding="utf-8")), encoding="utf-8")

    leftovers = [p for p in DST.rglob("*") if p.suffix == ".map" or "__min" in p.name]
    if leftovers:
        print("Beklenmeyen dosyalar:", leftovers, file=sys.stderr)
        return 1
    print(f"Hazır: {DST.relative_to(ROOT)}  ({sum(1 for _ in DST.rglob('*') if _.is_file())} dosya)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
