"use strict";
/* Dil seçici: kullanıcının seçtiği dili 1 yıl boyunca çerezde saklar; kök adres (/) bir sonraki girişte bu dile yönlenir. */
document.addEventListener("click", (e) => {
  const link = e.target instanceof Element ? e.target.closest("a[data-lang]") : null;
  if (!link) return;
  try {
    document.cookie = `gl_lang=${link.dataset.lang}; path=/; max-age=31536000; SameSite=Lax`;
  } catch { /* çerezler kapalı olabilir */ }
});
