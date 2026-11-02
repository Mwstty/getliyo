"use strict";
/* Yasal sayfalardaki [data-site] alanlarını site-config.js'ten doldurur. Boş kalanlar sarı görünür. */
(function () {
  const S = window.SITE || {};
  const lang = document.documentElement.lang;
  // İsteğe bağlı alanlar (ör. vergi/sicil no) boşsa hiç gösterilmez; var gibi görünmesin
  document.querySelectorAll("[data-optional]").forEach((el) => { if (!S[el.dataset.optional]) el.remove(); });
  const labels = {
    tr: { operator: "İŞLETMECİ ADI/UNVANI", email: "E-POSTA", address: "ADRES", taxOrTradeNo: "VERGİ/TİCARET SİCİL NO", updated: "TARİH" },
    en: { operator: "OPERATOR NAME", email: "EMAIL", address: "ADDRESS", taxOrTradeNo: "TAX/TRADE REGISTRY NO", updated: "DATE" },
    ar: { operator: "اسم المشغّل", email: "البريد الإلكتروني", address: "العنوان", taxOrTradeNo: "الرقم الضريبي/التجاري", updated: "التاريخ" },
  }[lang] || {};
  document.querySelectorAll("[data-site]").forEach((el) => {
    const key = el.dataset.site;
    const value = S[key];
    if (value) el.textContent = value;
    else { el.textContent = `[${labels[key] || key.toUpperCase()}]`; el.classList.add("empty-field"); }
  });
})();
