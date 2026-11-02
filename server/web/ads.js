"use strict";
/* Reklam alanları ve istatistik kodu. Kodları site-config.js içine yapıştır; burada değişiklik gerekmez.
   Reklam/istatistik kodları yalnızca çerez onayı verildikten sonra yüklenir.
   Her reklam "Reklam" etiketiyle işaretlenir (ticari reklamın açıkça belirtilmesi gerekir). */
(function () {
  const S = window.SITE || {};
  const adsCfg = S.ads || {};
  const consent = window.Consent || { get: () => ({ ads: true, analytics: true }), onChange() {} };
  const filled = new Set();
  let analyticsLoaded = false;

  function inject(el, code) {
    el.classList.remove("placeholder");
    el.innerHTML = '<span class="ad-tag">Reklam</span><div class="ad-body"></div>';
    // createContextualFragment, reklam kodundaki <script> etiketlerinin çalışmasını sağlar
    el.querySelector(".ad-body").append(document.createRange().createContextualFragment(code));
  }

  function render() {
    const allowed = consent.get();
    document.querySelectorAll(".ad[data-slot]").forEach((el) => {
      if (filled.has(el)) return;
      const code = adsCfg.enabled ? (adsCfg.slots || {})[el.dataset.slot] : "";
      if (code && allowed.ads) {
        inject(el, code);
        filled.add(el);
      } else if (!code && adsCfg.showPlaceholders) {
        el.classList.add("placeholder");
        el.innerHTML = '<span class="ad-tag">Reklam</span><span class="ad-hint">Reklam alanı</span>';
      } else if (!code) {
        el.remove();  // reklam yoksa boş kutu bırakma
      } else {
        el.innerHTML = "";  // kod var ama onay yok: alan boş kalır
        el.hidden = true;
      }
    });

    const a = S.analytics || {};
    if (a.enabled && a.code && !analyticsLoaded && (!a.needsConsent || allowed.analytics)) {
      analyticsLoaded = true;
      document.head.append(document.createRange().createContextualFragment(a.code));
    }
  }

  // onay verilince gizlenen alanları geri aç
  consent.onChange(() => {
    document.querySelectorAll(".ad[hidden]").forEach((el) => { el.hidden = false; });
    render();
  });
  render();

  const c = document.getElementById("copyright");
  if (c) c.textContent = `© ${new Date().getFullYear()} ${S.name || ""}`;
})();
