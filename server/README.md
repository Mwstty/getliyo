# getliyo — Sunucu

Masaüstü uygulamasının indirme çekirdeğini HTTP API + web arayüzü olarak sunar.
PySide6 gerekmez.

## Yerelde çalıştırma
```
pip install -r requirements.txt
python -m server          # http://127.0.0.1:8000
```
`GETLIYO_API_KEYS` tanımlı değilse **kimlik doğrulama kapalıdır** (yerel kullanım). Sunucuyu internete
açarken mutlaka tanımla. API dokümanı varsayılan olarak kapalıdır (`GETLIYO_ENABLE_DOCS=1` ile açılır).

## VPS'e kurulum
Docker dosyaları temizlik sırasında kaldırıldı (git geçmişinde `a24744c` commit'inde duruyor). `python -m server` ile çalıştırıp önüne HTTPS sağlayan bir ters vekil (Caddy/nginx) koyun; sunucu yalnızca `127.0.0.1`'e bağlanmalıdır.

## Ortam değişkenleri
| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `GETLIYO_API_KEYS` | (boş = anahtarsız) | Virgülle ayrılmış API anahtarları. Her anahtarın işleri ayrıdır |
| `GETLIYO_DATA_DIR` | `server-data` | İş veritabanı, anahtar, gizli imza anahtarı |
| `GETLIYO_DOWNLOAD_DIR` | `<data>/downloads` | İndirilen dosyalar |
| `GETLIYO_MAX_CONCURRENT` | 2 | Aynı anda çalışan indirme |
| `GETLIYO_MAX_ACTIVE_PER_KEY` | 5 | Anahtar başına bekleyen+çalışan iş |
| `GETLIYO_MAX_FILESIZE_MB` | 2000 | Disk korumak için dosya boyutu sınırı (0 = sınırsız). Akış sırasında da bayt olarak uygulanır |
| `GETLIYO_MAX_ENTRIES` | 25 | Tek istekte en fazla playlist/galeri öğesi |
| `GETLIYO_ALLOW_PRIVATE_URLS` | kapalı | SADECE test için; açıkken SSRF koruması kapanır |
| `GETLIYO_RETENTION_MINUTES` | 15 | Biten dosyaların ve kayıtların saklanma süresi (dakika, 5–15 arası; üst sınır 15). Temizlik dakikada bir çalışır |
| `GETLIYO_ANALYZE_PER_MINUTE` | 30 | Anahtar başına istek sınırı |
| `GETLIYO_RATE_LIMIT_MBPS` | 0 | İndirme hız sınırı |
| `GETLIYO_PROXY_URL` | — | Çıkış proxy'si (VPS IP'si engellenirse) |
| `GETLIYO_BLOCKED_DOMAINS` | — | Telif bildirimi sonrası engellenecek alan adları (virgülle) |
| `GETLIYO_MAX_ACTIVE_TOTAL` | 20 | Tüm ziyaretçiler için toplam bekleyen+çalışan iş sınırı |
| `GETLIYO_LOG_RETENTION_DAYS` | 30 | Erişim kaydı (IP, zaman, yol, durum) saklama süresi — hukuki gereklilikle uyumlu belirle |
| `GETLIYO_ENABLE_DOCS` | kapalı | `/api/docs` ve `openapi.json` |
| `GETLIYO_CSP` | sıkı varsayılan | Content-Security-Policy. Reklam/analytics ağı kullanacaksan ağın alan adlarını buraya ekle |
| `GETLIYO_SITE_URL` | (istekten türetilir) | Sitenin açık adresi, ör. `https://getliyo.com`. canonical, sitemap ve paylaşım görseli için; yayında mutlaka tanımla |
| `GETLIYO_CORS_ORIGINS` | — | Başka bir web sitesinden çağrılacaksa izinli origin'ler |
| `GETLIYO_HOST` / `GETLIYO_PORT` | 127.0.0.1 / 8000 | Dinleme adresi |
| `GETLIYO_IG_APP_SECRET` | — | Meta App Dashboard → App Secret. Webhook imza doğrulaması için (`X-Hub-Signature-256`) |
| `GETLIYO_IG_VERIFY_TOKEN` | — | Webhook kurulumunda Meta'ya girilen rastgele dize (GET doğrulama adımı) |
| `GETLIYO_IG_PAGE_TOKEN` | — | Page access token (Graph API çağrıları + private reply göndermek için) |
| `GETLIYO_IG_BUSINESS_ID` | — | Instagram Business/Creator hesabının Instagram-scoped ID'si (IGSID) |
| `GETLIYO_PUBLIC_BASE_URL` | (boşsa `GETLIYO_SITE_URL`) | İnternetten erişilen kök adres, ör. `https://getliyo.com` (sonda `/` yok). DM'e yazılan `/r/<belirteç>` sonuç bağlantısı bununla üretilir; ikisi de boşsa DM yanıtları kapalı kalır |

Dördü birden doluysa `/webhooks/instagram` (GET: Meta'nın doğrulama isteği, POST: mention + DM bildirimi) açılır;
biri bile eksikse uç nokta hiç kayıtlı olmaz (404) ve açılışta log'a eksik değişken ADLARI yazılır (değerler asla) —
bkz. `server/social/instagram.py`. DM akışı ayrıca `GETLIYO_PUBLIC_BASE_URL`/`GETLIYO_SITE_URL` ister.

## Instagram DM ile indirme (AŞAMA 7)
Kullanıcı Getliyo'nun profesyonel Instagram hesabına DM ile **herkese açık tek bir video bağlantısı** yazar
(YouTube, TikTok, Instagram, Facebook, Reddit… indirme motorunun desteklediği her kaynak). Sunucu:
1. `messages` webhook'unu alır; imza (`X-Hub-Signature-256`) doğrulanır, aynı `mid` ikinci kez işlenmez.
2. Mesajdan bağlantıyı ayıklar (0 bağlantı → yardım mesajı, 2+ farklı bağlantı → "tek bağlantı gönder").
   Web'deki `checked_url` kuralları aynen geçerlidir (SSRF, engelli alan adları).
3. Mevcut `JobManager` kuyruğuna alır (iş sahibi = gönderen kimliğinin özeti; kota ve hız sınırı geçerli).
   İş 20 sn'den uzun sürerse BİR kez "hazırlanıyor" yazılır.
4. İş bitince aynı konuşmaya `PUBLIC_BASE_URL/r/<belirteç>` bağlantısı yazılır. Belirteç = rastgele iş kimliği +
   bitiş zamanı + HMAC; bitiş = dosyanın silineceği an (`GETLIYO_RETENTION_MINUTES`, en çok 15 dk).
   Sayfa mevcut site çerçevesini ve reklam alanlarını kullanır; dosya silinmişse/süre dolmuşsa 410 ve anlaşılır hata gösterir.
5. Hata durumunda DM'e kısa, genel bir mesaj gider; iç hata ayrıntısı asla yazılmaz. Yanıt reddedilirse (ör. Meta'nın
   mesajlaşma penceresi kapandıysa) başka yol denenmez, yalnızca loglanır.

Konuşma eşlemesi (`<data>/ig_dm.db`) yanıt gönderilince silinir; yinelenen-olay kaydı (yalnızca `mid`) 24 saat tutulur.

### Meta tarafında yapılacaklar (senin hesabınla)
1. Instagram hesabını **Professional (Business/Creator)** yap ve bir Facebook Sayfası'na bağla.
2. developers.facebook.com → uygulama oluştur (tür: Business) → **Instagram** (Messenger API for Instagram) ürününü ekle.
3. İzinler: `instagram_basic`, `instagram_manage_messages`, `pages_show_list`, `pages_manage_metadata`
   (Sayfa token'ı akışı için `pages_messaging`). Uygulama *Development* modunda yalnızca uygulama rolü olan hesaplar
   mesaj atabilir; herkese açmak için **App Review + Business Verification (Advanced Access)** gerekir.
4. Sayfa/hesap için access token üret → `GETLIYO_IG_PAGE_TOKEN`; App Secret → `GETLIYO_IG_APP_SECRET`;
   IG hesap kimliği → `GETLIYO_IG_BUSINESS_ID`; kendin seçtiğin rastgele dize → `GETLIYO_IG_VERIFY_TOKEN`.
5. Webhooks → Instagram → Callback URL: `https://<PUBLIC_BASE_URL>/webhooks/instagram`, Verify Token: yukarıdaki dize,
   alanlar: **`messages`** (ve mention için `mentions`). Hesabı uygulamaya abone et.
6. Meta belgeleri sık değişir; sürüm (`GRAPH_API` sabiti) ve izin adlarını canlıya almadan önce güncel belgeden kontrol et.

### Yerel geliştirme
Sunucu yerel bilgisayarda çalışırken Meta'nın webhook'u çağırabilmesi için internete açık HTTPS adres gerekir:
bir tünel (ör. `cloudflared tunnel --url http://127.0.0.1:8000` veya `ngrok http 8000`) başlat, çıkan `https://…`
adresini hem `GETLIYO_PUBLIC_BASE_URL` hem Meta'daki Callback URL'de kullan. Tünel kurmak/yayınlamak bu projenin
parçası değildir; tünel kapanınca DM akışı çalışmaz.

## API
`GETLIYO_API_KEYS` tanımlıysa tüm istekler `Authorization: Bearer <anahtar>` (ya da `X-API-Key`) ister.

| Metot | Yol | Açıklama |
|---|---|---|
| GET | `/api/health` | Canlılık (anahtarsız) |
| GET | `/api/status` | Yönetici bilgisi (yalnızca anahtar tanımlıyken) |
| POST | `/api/analyze` `{url}` | Medya ve format listesi |
| POST | `/api/jobs` `{url, preset?, entries?, format_id?}` | İndirme başlatır. preset: `best` `best_mp4` `h1080` `h720` `audio` |
| GET | `/api/jobs` | İşlerin listesi |
| GET | `/api/jobs/{id}` | Durum, yüzde, kalan süre, `download_url` |
| DELETE | `/api/jobs/{id}` | Çalışanı iptal eder, bitenin dosyasını siler |
| GET | `/api/jobs/{id}/file` | Dosya. `download_url` içindeki imza 15 dk geçerlidir |

## Güvenlik notları
- Sunucu iç ağ/localhost/bulut metadata adreslerine istek atmaz (SSRF koruması). `python -m server`
  ile başlatıldığında doğrudan HTTP isteklerinin her adımı (yönlendirmeler, sayfadaki medya/küçük resim
  adresleri dahil) denetlenir. ayrıca DNS çözümleme anında da iç adresler reddedilir; böylece yt-dlp'nin kendi
  istekleri ve DNS rebinding de kapsanır. İkinci savunma olarak ağ katmanında iç ağa ve bulut metadata
  adresine çıkışı kesin (eski `egress-firewall.sh` betiği git geçmişinde `a24744c` commit'inde duruyor).
  Dış çıkış proxy'si kullanıyorsanız `GETLIYO_PROXY_URL` adresi otomatik istisna olur.
- Anahtarlar sabit zamanlı karşılaştırılır, loglanmaz; iş sahipliği anahtarın özetiyle tutulur.
- Genel kullanıma açmadan önce telif/platform şartları sorumluluğunu değerlendirin.

## Gizlilik ve günlükler
- Erişim kaydı `<data>/logs/access.log` dosyasına yazılır: zaman, IP, yöntem, yol, durum kodu. **İstek gövdesi ve bağlantılar yazılmaz.** Süreye göre döner ve silinir.
- Uygulama hataları ayrıca `app.log` dosyasına yazılır (bağlantılarda yalnızca alan adı).
- Anahtarsız modda her sayfa yüklemesi rastgele bir ziyaretçi kimliği üretir (kalıcı değildir); indirme listeleri buna göre ayrılır ve sayfa yenilenince sıfırlanır. Kimlik oluşturup limit aşmaya karşı IP başına ayrıca hız sınırı vardır.

## Çok dillilik (TR / EN / AR)
- Adresler: `/tr/`, `/en/`, `/ar/` (ana sayfa) ve `/{dil}/terms|privacy|copyright|cookies|contact` (yasal sayfalar). Eski `/legal/*.html` adresleri `/tr/...`'ye 301 ile yönlenir.
- Metinler `server/web/locales/{dil}.json` içindedir (üç dosyada aynı anahtarlar olmalı; test bunu denetler). Şablonlar `server/templates/`, yasal sayfa metinleri `server/pages/{dil}/` altındadır.
- **Yeni dil eklemek:** `locales/xx.json`, `pages/xx/*.html` + `meta.json` ekle, `server/site.py` içindeki `LANGS`, `LANG_NAMES`, `OG_LOCALE` (Arapça gibi sağdan sola diller için `RTL`) değerlerini güncelle.
- Arapça için `dir="rtl"` otomatik verilir; her sayfada `hreflang` etiketleri ve sitemap'te dil alternatifleri bulunur.
- **`/` yönlendirmesi** sırası: `gl_lang` çerezi (dil seçici tıklanınca 1 yıl saklanır) → `CF-IPCountry` (TR → `/tr/`, `SA AE EG QA KW BH OM JO IQ MA DZ TN LY LB SY YE SD PS MR` → `/ar/`) → `Accept-Language` → `/en/`. Arama motoru botları yönlendirilmez; `/`'te İngilizce sayfayı (200) görür.
- `CF-IPCountry` yalnızca Cloudflare arkasında gelir; yerelde `Accept-Language`'e düşülür.

## Instagram
- Yalnızca herkese açık gönderi (`/p/`), Reels (`/reel/`), IGTV (`/tv/`) ve hikaye (`/stories/...`) bağlantıları kabul edilir; profil, giriş sayfası vb. `ig_invalid` hatası verir (`server/instagram.py`). Hiçbir yerde Instagram şifresi istenmez.
- İndirme motoru yt-dlp tabanlıdır. Instagram giriş gerektiren içerikleri ve sık istekleri engelleyebilir; bu durumda kullanıcıya `forbidden` mesajı gösterilir. yt-dlp'yi güncel tutmak çalışma oranını belirler.
- Hız sınırı: anahtar/ziyaretçi başına ve IP başına dakikada sınırlı istek (`GETLIYO_ANALYZE_PER_MINUTE`); aşılırsa 429 ve kullanıcı dilinde mesaj.

## Yayına alma kontrol listesi (VPS + Cloudflare)
1. **Alan adı:** Namecheap veya Cloudflare Registrar'dan, **WHOIS gizliliği açık** şekilde al. (WHOIS gizliliği yalnızca halka açık sorguyu gizler; yasal olarak künyendeki bilgiler gerçek olmalıdır.)
2. **DNS:** Alan adını Cloudflare'e taşı; `A`/`AAAA` kayıtlarını **Proxied (turuncu bulut)** yap.
3. **Origin koruması:** VPS güvenlik duvarında 80/443'e yalnızca [Cloudflare IP aralıklarından](https://www.cloudflare.com/ips/) izin ver; SSH'ı ayrıca kısıtla. Uygulamayı `GETLIYO_HOST=127.0.0.1` ile çalıştırıp önüne Nginx/Caddy koy. `proxy_headers` açıktır; gerçek IP için `CF-Connecting-IP` başlığına güven (yalnızca Cloudflare IP'lerinden gelen istekte).
4. **SSL:** Cloudflare'de SSL/TLS modunu **Full (strict)** yap; origin'e Cloudflare Origin sertifikası kur. "Always Use HTTPS" ve HSTS'yi aç.
5. **WAF/bot:** Cloudflare'de Managed Rules, Bot Fight Mode ve `/api/*` için hız sınırlama kuralı (ör. IP başına dakikada 30) etkinleştir. Arama motoru botlarını engelleme.
6. **Ayarlar:** `GETLIYO_SITE_URL=https://alanadin.com`. Herkese açık sitede `GETLIYO_API_KEYS` **tanımlama**: anahtar tanımlanırsa site giriş ekranı ister; anahtarsız modda her ziyaretçi rastgele kimlikle ve IP başına hız sınırıyla kullanır. İmza sırrı `<GETLIYO_DATA_DIR>/secret.key` dosyasında otomatik üretilir (yedekle).
7. **Yasal alanlar:** `server/web/site-config.js` içindeki `operator`, `email`, `address` (ve varsa `taxOrTradeNo`) alanlarını doldur; boşlarsa yasal sayfalarda sarı köşeli parantezle görünür. Reklam kodları yalnızca çerez onayından sonra yüklenir.
