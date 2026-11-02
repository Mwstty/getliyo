# getliyo

Windows için video, ses ve görsel indirme uygulaması. YouTube, Instagram, TikTok, X, Pinterest ve yt-dlp'nin desteklediği diğer sitelerden indirir. Arayüz PySide6 ile yazıldı, indirme motoru yt-dlp tabanlıdır.

Uygulama ayrıca yerel bir web sunucusu (FastAPI) çalıştırır; ayrıntılar için [server/README.md](server/README.md).

## Özellikler
- Bağlantıyı yapıştır, analiz et, çözünürlük/format seç, indir
- Hızlı ön ayarlar: en iyi kalite, MP4, 1080p, 720p, yalnızca ses
- Playlist ve galeri desteği, indirme geçmişi
- Chrome eklentisi ile sağ tıkla indirme (`browser-extension/`)
- Gömülü yerel web arayüzü (`server/`)

## Gereksinimler
- Windows 10/11
- Python 3.12 (3.13 ile de test edildi)
- İnternet bağlantısı (ilk kurulumda FFmpeg ve Deno indirilir)

## Kurulum ve çalıştırma
```
scripts\setup.bat     # sanal ortam, bağımlılıklar, FFmpeg/Deno (bin\ klasörüne)
scripts\run.bat       # uygulamayı başlatır
```
Web sitesini/sunucuyu çalıştırmak için `scripts\run_server.bat` (gerekirse kurulumu yapar, FFmpeg/Deno'yu ilk açılışta kendisi indirir, tarayıcıyı açar). Otomatik indirmeyi kapatmak için `GETLIYO_AUTO_FETCH=0`.

Elle çalıştırmak için: `.venv\Scripts\python.exe -m app.main`

## Test
```
.venv\Scripts\python.exe -m pytest -q
```

## Derleme (EXE + kurulum programı)
```
scripts\build.bat
```
Sırasıyla yt-dlp'yi günceller, testleri çalıştırır, web paketini küçültür, kaynağı PyArmor ile karartır, PyInstaller ile `dist\getliyo.exe` üretir. [Inno Setup](https://jrsoftware.org/isinfo.php) kuruluysa `Output\getliyo-setup.exe` de oluşur. `scripts\clean.bat` derleme çıktılarını temizler.

## Klasör yapısı
| Klasör | İçerik |
|---|---|
| `app/` | Masaüstü uygulaması (arayüz, indiriciler, ayarlar, geçmiş) |
| `server/` | Yerel web sunucusu ve web arayüzü |
| `browser-extension/` | Chrome eklentisi |
| `bin/` | FFmpeg, FFprobe, Deno (git'e girmez, `setup.bat` indirir) |
| `installer/` | Inno Setup betiği ve kullanım kılavuzu |
| `scripts/` | Kurulum, derleme ve yardımcı betikler |
| `tests/` | pytest testleri |

## Lisans
[LICENSE](LICENSE) dosyasına bakın.
