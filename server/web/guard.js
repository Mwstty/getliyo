"use strict";
/* Sağ tık menüsünü engeller (caydırıcı arayüz önlemi; güvenlik sağlamaz).
   Yazı alanlarında (bağlantı, anahtar kutusu) menü açık kalır; yoksa dokunmatik ekranda yapıştırma imkânsız olur. */
document.addEventListener("contextmenu", (e) => {
  const t = e.target;
  if (t instanceof Element && t.closest("input, textarea, [contenteditable='true']")) return;
  e.preventDefault();
}, true);
