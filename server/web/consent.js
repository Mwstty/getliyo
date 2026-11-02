"use strict";
/* Çerez onayı. Banner yalnızca reklam ya da (onay gerektiren) istatistik açıkken gösterilir.
   "Reddet" ve "Kabul et" eşit görünürlükte; reddedilirse reklam/istatistik kodları hiç yüklenmez. */
(function () {
  const S = window.SITE || {};
  const KEY = "getliyo_consent";
  const VERSION = 1;
  const listeners = [];

  const needed = !!((S.ads && S.ads.enabled) || (S.analytics && S.analytics.enabled && S.analytics.needsConsent));

  function read() {
    try {
      const v = JSON.parse(localStorage.getItem(KEY) || "null");
      return v && v.v === VERSION ? v : null;
    } catch { return null; }
  }
  function write(value) {
    try { localStorage.setItem(KEY, JSON.stringify({ v: VERSION, ...value, ts: Date.now() })); } catch { /* depolama kapalı */ }
  }

  const banner = document.getElementById("cookie-banner");
  const link = document.getElementById("cookie-link");

  const api = {
    needed,
    /** Mevcut karar. Onay gerekmiyorsa her şeye izin var sayılır. */
    get() {
      if (!needed) return { ads: true, analytics: true };
      const c = read();
      return c ? { ads: !!c.ads, analytics: !!c.analytics } : { ads: false, analytics: false };
    },
    onChange(cb) { listeners.push(cb); },
    open() { if (banner) { banner.hidden = false; document.getElementById("cookie-reject").focus(); } },
  };

  function decide(accepted) {
    write({ ads: accepted, analytics: accepted });
    if (banner) banner.hidden = true;
    listeners.forEach((cb) => cb(api.get()));
  }

  if (needed && banner) {
    if (link) {
      link.hidden = false;
      link.addEventListener("click", (e) => { e.preventDefault(); api.open(); });
    }
    document.getElementById("cookie-accept").addEventListener("click", () => decide(true));
    document.getElementById("cookie-reject").addEventListener("click", () => decide(false));
    if (!read()) banner.hidden = false;
  }
  window.Consent = api;
})();
