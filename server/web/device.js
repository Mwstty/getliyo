"use strict";
/* Cihaz türünü algılar ve <html data-device="mobile|tablet|desktop"> olarak işaretler.
   Düzen genişliğe göre zaten uyum sağlar (style.css); bu işaret dokunmatik cihazlara özel ayarlar içindir. */
(function () {
  const root = document.documentElement;
  const ua = navigator.userAgent || "";

  function kind() {
    const touchMac = /Macintosh/.test(ua) && navigator.maxTouchPoints > 1;  // iPadOS kendini Mac olarak tanıtır
    if (/iPad|Tablet|PlayBook|Silk/i.test(ua) || touchMac || (/Android/i.test(ua) && !/Mobile/i.test(ua))) return "tablet";
    if (/iPhone|iPod|Android.*Mobile|Windows Phone|Mobile/i.test(ua)) return "mobile";
    if (window.matchMedia("(pointer: coarse) and (hover: none)").matches) {  // UA'sı belirsiz dokunmatik cihaz
      return Math.min(screen.width, screen.height) < 600 ? "mobile" : "tablet";
    }
    return "desktop";
  }

  function apply() {
    root.dataset.device = kind();
    root.dataset.orientation = window.innerHeight > window.innerWidth ? "portrait" : "landscape";
  }

  apply();
  window.addEventListener("resize", apply, { passive: true });
  window.addEventListener("orientationchange", apply);
})();
