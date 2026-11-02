/* Site bilgileri — TEK YERDEN düzenle. Hukuki sayfalar bu değerleri otomatik doldurur.
   Boş bıraktığın alanlar hukuki sayfalarda [SARI KÖŞELİ PARANTEZ] olarak görünür; yayına almadan önce doldur. */
/* DENEME reklamı üretici (gerçek ağ kodu gelince bu fonksiyonla birlikte silinebilir). */
function testAd(title, text, cta) {
  return '<div class="ad-test"><div class="ad-art">★</div><div><strong>' + title + '</strong><span class="t">' + text +
    '</span></div><span class="ad-cta">' + cta + '</span></div>';
}

window.SITE = {
  name: "getliyo",
  operator: "",   // Gerçek kişi adı-soyadı veya şirket unvanı (5651 sayılı Kanun'a göre kimlik bilgisi zorunlu)
  email: "",      // Telif/içerik bildirimleri ve KVKK başvuruları için e-posta
  address: "",    // Tebligat adresi
  taxOrTradeNo: "", // Vergi no / ticaret sicil no (varsa)
  updated: "09.10.2026",
  termsVersion: "1",  // Şartları değiştirirsen artır; kullanıcılardan yeniden onay istenir

  /* REKLAM ALANLARI
     enabled: true yapıp her alana ağın verdiği kodu yapıştır (HTML + <script> olabilir).
     Reklam kodları, kullanıcı çerez bannerında "Kabul et" demeden YÜKLENMEZ.
     Kod boşsa ve showPlaceholders true ise "Reklam alanı" kutusu gösterilir (geliştirme için);
     yayında showPlaceholders: false yap. Slotlar: top, side, inline, bottom. */
  ads: {
    enabled: true,   // DENEME: gerçek reklam kodu gelince slotları o kodla değiştir
    showPlaceholders: true,
    slots: {
      top: testAd("Reklam alanınız burada", "Bu bir deneme reklamıdır. 728×90 üst alan.", "Detaylar"),
      side: testAd("Deneme reklamı", "Yan sütun alanı. Gerçek reklam kodu gelince burası değişir.", "Göz at"),
      inline: testAd("Marka adınız burada", "Bu bir deneme reklamıdır. İndirme alanının altındaki geniş reklam.", "Keşfet"),
      bottom: testAd("Alt alan deneme reklamı", "Sayfa sonu için ayrılmış reklam alanı.", "Detaylar"),
    },
  },

  /* İSTATİSTİK (Analytics)
     code: servisin verdiği <script> parçası (Google Analytics, Plausible, Umami, Cloudflare Web Analytics...).
     needsConsent: çerez kullanan servisler (Google Analytics gibi) için true bırak; çerezsiz servislerde false yapabilirsin. */
  analytics: {
    enabled: false,
    needsConsent: true,
    code: "",
  },
};
