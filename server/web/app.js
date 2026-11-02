"use strict";

const $ = (id) => document.getElementById(id);
const KEY_STORE = "getliyo_api_key";

const LANG = document.documentElement.lang || "en";
let T = {};  // /locales/{dil}.json içeriği
// Dil dosyası yüklenemezse bile ekranda ham anahtar yerine okunur metin görünsün
const FALLBACK = {
  "msg.analyzing": "Bağlantı inceleniyor...", "msg.preparing": "İndirme hazırlanıyor...", "msg.converting": "Dönüştürülüyor...",
  "msg.downloading": "İndiriliyor", "msg.ready": "İndirme hazır.", "msg.failed": "İndirme başarısız oldu. Lütfen tekrar deneyin.",
  "msg.pick": "Önce bir seçenek seç.", "msg.invalid": "Geçerli bir bağlantı girin.", "msg.paste_first": "Önce bir bağlantı yapıştır.",
  "btn.retry": "Tekrar dene", "btn.clear": "Temizle", "msg.paste_empty": "Panoda bağlantı yok.", "btn.save": "Dosyayı kaydet", "btn.get": "{fmt} Olarak İndir", "btn.get_all": "Tümünü İndir",
  "err.generic": "Bir sorun oluştu. Lütfen biraz sonra tekrar deneyin.", "err.download_failed": "İndirme başarısız oldu. Lütfen tekrar deneyin.",
};
/** Çeviri: t("anahtar", {n: 3}) — bulunamazsa anahtarın kendisi görünür. */
function t(key, vars = {}) {
  return String(T[key] ?? FALLBACK[key] ?? "").replace(/\{(\w+)\}/g, (_, k) => (k in vars ? vars[k] : `{${k}}`));
}

let apiKey = "";
let pollTimer = null;

try { apiKey = localStorage.getItem(KEY_STORE) || ""; } catch { /* depolama kapalı olabilir */ }

// İndirme listeni diğer ziyaretçilerden ayıran rastgele kimlik. Yalnızca bu sayfa açıkken bellekte durur:
// sayfa yenilenince yeni kimlik üretilir, böylece önceki indirmeler listede görünmez (sunucuda 15 dakika içinde silinir).
const VISITOR = (() => {
  const bytes = crypto.getRandomValues(new Uint8Array(24));
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
})();

async function api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(apiKey ? { Authorization: `Bearer ${apiKey}` } : {}),
      ...(VISITOR ? { "X-Visitor-Id": VISITOR } : {}),
      ...(options.headers || {}),
    },
  });
  if (res.status === 401) { showLogin(t("login.bad_key")); throw new Error("401"); }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(errorText(res.status, data));
  return data;
}

/** Sunucu hata kodunu (code) ya da durumunu seçili dildeki mesaja çevirir. */
function errorText(status, data) {
  if (data.code && T[`err.${data.code}`]) return t(`err.${data.code}`);
  if (status === 429) return t("err.rate");
  return t("err.generic");
}

function show(el, visible) { el.hidden = !visible; }
function setMessage(text, isError = false, percent = null) {
  const el = $("message");
  el.textContent = text;
  el.className = isError ? "msg err" : percent == null ? "msg" : "msg prog";
  if (percent == null) el.style.removeProperty("--p"); else el.style.setProperty("--p", String(Math.max(0, Math.min(100, percent))));
}

function fmtSize(n) {
  if (!n) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i ? 1 : 0)} ${units[i]}`;
}
function fmtTime(s) {
  if (s == null) return "";
  const m = Math.floor(s / 60);
  return m ? t("time.min", { m, s: Math.round(s % 60) }) : t("time.sec", { s: Math.round(s) });
}

// ---------------------------------------------------------------- kullanım şartı onayı
const TERMS_KEY = "getliyo_terms";
const termsVersion = () => (window.SITE && window.SITE.termsVersion) || "1";
function termsAccepted() {
  try { return localStorage.getItem(TERMS_KEY) === termsVersion(); } catch { return false; }
}
function requireTerms() {
  if (termsAccepted()) return Promise.resolve(true);
  const dlg = $("terms"), check = $("terms-check"), ok = $("terms-ok");
  check.checked = false; ok.disabled = true;
  check.onchange = () => { ok.disabled = !check.checked; };
  return new Promise((resolve) => {
    $("terms-cancel").onclick = () => { dlg.close(); resolve(false); };
    dlg.oncancel = () => resolve(false);
    $("terms-form").onsubmit = () => {
      try { localStorage.setItem(TERMS_KEY, termsVersion()); } catch { /* yoksay */ }
      resolve(true);  // method="dialog" formu pencereyi kendisi kapatır
    };
    dlg.showModal();
  });
}

// ---------------------------------------------------------------- giriş
function showLogin(error = "") {
  show($("login"), true); show($("app"), false); show($("logout"), false);
  const el = $("login-error");
  el.textContent = error; show(el, !!error);
  clearInterval(pollTimer); pollTimer = null;
}

async function start() {
  try {
    await api("/api/jobs");  // anahtar gerekiyorsa 401 ile giriş ekranı açılır
  } catch (e) { if (e.message !== "401") showLogin(e.message); return; }
  show($("login"), false); show($("app"), true); show($("logout"), !!apiKey);
}

$("login-form").addEventListener("submit", (e) => {
  e.preventDefault();
  apiKey = $("key-input").value.trim();
  try { localStorage.setItem(KEY_STORE, apiKey); } catch { /* yoksay */ }
  $("key-input").value = "";
  start();
});

// ---------------------------------------------------------------- "Yapıştır" / "Temizle"
/** Panoyu okur: tarayıcı API'si, olmazsa (Android WebView) uygulamanın yerel köprüsü. */
async function readClipboard() {
  if (window.GetliyoNative) {  // Android uygulaması: önce yerel köprü (WebView'da tarayıcı API'si takılıp kalabiliyor)
    try { return String(window.GetliyoNative.getClipboard() || "").trim(); } catch { /* tarayıcı API'sine düş */ }
  }
  if (navigator.clipboard && navigator.clipboard.readText) {
    const text = await Promise.race([navigator.clipboard.readText(), new Promise((_, no) => setTimeout(() => no(new Error("timeout")), 2000))]);
    return String(text || "").trim();
  }
  throw new Error("clipboard");
}
const urlInput = $("url-input"), clearBtn = $("clear-btn");
function syncClear() { show(clearBtn, urlInput.value.trim().length > 0); }
$("paste-btn").addEventListener("click", async () => {
  try {
    const text = await readClipboard();
    if (!text) { setMessage(t("msg.paste_empty"), true); urlInput.focus(); return; }
    resetOptions();
    urlInput.value = text; urlInput.removeAttribute("aria-invalid"); syncClear();
    if (/^(https?:\/\/)?[^\s/]+\.[^\s/]+/i.test(text) && !/\s/.test(text)) $("url-form").requestSubmit();  // bağlantıysa hemen incele
    else urlInput.focus();
  } catch { setMessage(t("msg.paste_denied"), true); urlInput.focus(); }
});
clearBtn.addEventListener("click", () => { urlInput.value = ""; resetOptions(); syncClear(); urlInput.focus(); });
urlInput.addEventListener("input", syncClear);

$("logout").addEventListener("click", () => {
  apiKey = "";
  try { localStorage.removeItem(KEY_STORE); } catch { /* yoksay */ }
  showLogin();
});

// ---------------------------------------------------------------- analiz
function busy(on) { $("quick-btn").disabled = on; $("get-btn").disabled = on; }

/** Alanı doğrular; geçerliyse temiz URL'yi, değilse null döndürür (hata mesajını gösterir). */
function readUrl() {
  const input = $("url-input");
  let value = input.value.trim();
  const fail = (text) => { input.setAttribute("aria-invalid", "true"); setMessage(text, true); input.focus(); return null; };
  if (!value) return fail(t("msg.paste_first"));
  if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(value) && value.includes(".")) value = `https://${value}`;  // "site.com/x" yapıştırılırsa
  try {
    const u = new URL(value);
    if (u.protocol !== "http:" && u.protocol !== "https:") throw new Error();
  } catch { return fail(t("msg.invalid")); }
  input.removeAttribute("aria-invalid");
  input.value = value;
  return value;
}
$("url-input").addEventListener("input", () => $("url-input").removeAttribute("aria-invalid"));

// ---------------------------------------------------------------- 1) bağlantıyı incele, 2) seçenekleri göster
const optionsBox = $("options"), optList = $("opt-list"), getBtn = $("get-btn");
let current = null;       // son analiz sonucu
let choices = [];         // gösterilen seçenekler
let picked = null;        // seçili seçenek
let runId = 0;            // eski istek sonuçlarının yeni durumu ezmesini engeller

function resetOptions() {
  runId++; current = null; choices = []; picked = null;
  clearInterval(pollTimer); pollTimer = null;
  optList.replaceChildren(); show(optionsBox, false); setMessage(""); busy(false);
}
$("url-input").addEventListener("input", () => {
  $("url-input").removeAttribute("aria-invalid");
  if (current && $("url-input").value.trim() !== current.url) resetOptions();
});

/** Backend'in gerçekten sunduğu formatlardan, içerik türüne uygun seçenekleri çıkarır. */
function buildChoices(info) {
  if (info.entries.length > 1) {
    return [{ key: "all", container: "", kind: "all", desc: t("opt.all", { n: info.entries.length }), preset: "best" }];
  }
  const entry = info.entries[0], list = [], seen = new Set();
  const fmts = entry.formats || [];
  if (entry.kind === "video") {
    const byRes = new Map();
    for (const f of fmts.filter((x) => x.kind === "video")) {
      const cur = byRes.get(f.resolution);
      if (!cur || (f.codec === "AVC" && cur.codec !== "AVC")) byRes.set(f.resolution, f);  // MP4 için en uyumlu codec
    }
    for (const f of byRes.values()) list.push(choiceOf(f, "opt.video"));
    const mp3 = fmts.find((x) => x.kind === "audio" && x.container === "mp3");
    if (mp3) list.push(choiceOf(mp3, "opt.audio"));
  } else if (entry.kind === "audio") {
    const audios = fmts.filter((x) => x.kind === "audio");
    const mp3 = audios.find((x) => x.container === "mp3");
    for (const f of (mp3 ? [mp3] : audios)) list.push(choiceOf(f, "opt.audio"));
  } else {
    for (const f of fmts.filter((x) => x.kind === "image")) {
      if (seen.has(f.container)) continue;
      seen.add(f.container); list.push(choiceOf(f, "opt.image"));
    }
  }
  return list;
}
function choiceOf(f, labelKey) {
  const size = f.filesize ? `${f.size_estimated ? "~" : ""}${fmtSize(f.filesize)}` : "";
  const desc = [t(labelKey), f.resolution].filter(Boolean).join(" · ");
  return { key: f.format_id, container: (f.container || "").toUpperCase(), kind: f.kind, desc, size, formatId: f.format_id };
}

function fmtDuration(sec) {
  sec = Math.round(sec);
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  return (h ? `${h}:${String(m).padStart(2, "0")}` : `${m}`) + `:${String(s).padStart(2, "0")}`;
}
function renderOptions(info) {
  choices = buildChoices(info);
  optList.replaceChildren();
  $("opt-meta").textContent = [info.title, info.uploader].filter(Boolean).join(" · ");
  const e0 = info.entries[0] || {}, thumb = info.thumbnail || e0.thumbnail, dur = info.duration || e0.duration;
  const img = $("opt-thumb"), durEl = $("opt-dur");
  img.hidden = !thumb; img.onerror = () => { img.hidden = true; };
  if (thumb) img.src = thumb; else img.removeAttribute("src");
  durEl.hidden = !dur; durEl.textContent = dur ? fmtDuration(dur) : "";
  show($("opt-preview"), !!(thumb || dur || info.title));
  choices.forEach((c, i) => {
    const label = document.createElement("label");
    label.className = "opt";
    const input = document.createElement("input");
    input.type = "radio"; input.name = "opt"; input.value = c.key;
    input.addEventListener("change", () => pick(c));
    const body = document.createElement("span");
    body.className = "opt-body";
    const tick = document.createElement("span"); tick.className = "opt-tick"; tick.setAttribute("aria-hidden", "true");
    const fmt = document.createElement("span"); fmt.className = "opt-fmt"; fmt.textContent = c.container;
    const desc = document.createElement("span"); desc.className = "opt-desc"; desc.textContent = c.desc;
    body.append(tick, fmt, desc);
    if (c.size) { const sz = document.createElement("span"); sz.className = "opt-size"; sz.textContent = c.size; body.append(sz); }
    label.append(input, body);
    optList.append(label);
    if (i === 0) { input.checked = true; pick(c); }  // varsayılan seçenek açıkça işaretli gelir
  });
  show(optionsBox, choices.length > 0);
  if (!choices.length) setMessage(t("err.no_media"), true);
}
function pick(c) {
  picked = c;
  getBtn.textContent = c.container ? t("btn.get", { fmt: c.container }) : t("btn.get_all");
}

$("url-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const url = readUrl();
  if (!url || !(await requireTerms())) return;
  resetOptions();
  const my = runId;
  busy(true); setMessage(t("msg.analyzing"));
  try {
    const info = await api("/api/analyze", { method: "POST", body: JSON.stringify({ url }) });
    if (my !== runId) return;
    current = info; setMessage(""); renderOptions(info);
    optList.querySelector("input:checked")?.focus({ preventScroll: true });
  } catch (err) { if (my === runId) setMessage(err.message, true); }
  if (my === runId) busy(false);
});

// ---------------------------------------------------------------- 3) seçilen formatı indir
getBtn.addEventListener("click", () => startDownload());

async function startDownload() {
  if (!current) return;
  if (!picked) { setMessage(t("msg.pick"), true); return; }
  const my = runId;
  busy(true); setMessage(t("msg.preparing"));
  const body = picked.preset ? { url: current.url, preset: picked.preset } : { url: current.url, format_id: picked.formatId };
  try {
    const { jobs } = await api("/api/jobs", { method: "POST", body: JSON.stringify(body) });
    if (my === runId) watchJobs(new Set(jobs.map((j) => j.id)), my);
  } catch (err) { if (my === runId) fail(err.message); }
}

function fail(text) {
  clearInterval(pollTimer); pollTimer = null; busy(false);
  setMessage(text || t("msg.failed"), true);
  const retry = document.createElement("button");
  retry.type = "button"; retry.className = "btn sm"; retry.textContent = t("btn.retry");
  retry.addEventListener("click", startDownload);
  $("message").append(retry);
}

/** Başlatılan işleri izler; ilerlemeyi gösterir, hazır olunca dosyayı indirir. */
function watchJobs(ids, my) {
  clearInterval(pollTimer);
  const tick = async () => {
    let jobs;
    try { ({ jobs } = await api("/api/jobs")); } catch (err) { if (my === runId) fail(err.message); return; }
    if (my !== runId) return;
    const mine = jobs.filter((j) => ids.has(j.id));
    const running = mine.find((j) => j.status === "queued" || j.status === "running");
    if (running) {
      if (running.status === "queued") setMessage(t("msg.preparing"));
      else if (running.percent != null && running.percent < 100) {
        let text = `${t("msg.downloading")} · %${running.percent.toFixed(0)}`;
        if (running.eta != null) text += ` · ${t("job.eta", { t: fmtTime(running.eta) })}`;
        setMessage(text, false, running.percent);
      } else setMessage(t("msg.converting"));
      return;
    }
    const ready = mine.filter((j) => j.download_url);
    const failed = mine.find((j) => j.status === "failed");
    if (!ready.length) { fail(failed && T[`err.${failed.error_code}`] ? t(`err.${failed.error_code}`) : t("err.download_failed")); return; }
    clearInterval(pollTimer); pollTimer = null; busy(false);
    setMessage(t("msg.ready"));
    urlInput.value = ""; syncClear(); show(optionsBox, false); current = null; picked = null;  // sıradaki bağlantı için kutu temiz
    for (const j of ready) {
      const a = document.createElement("a");
      a.href = j.download_url; a.setAttribute("download", "");
      a.className = "btn primary big"; a.textContent = t("btn.save");
      $("message").append(a);  // otomatik indirme engellenirse elle başlatılabilir
      a.click();
    }
  };
  pollTimer = setInterval(tick, 1500);
  tick();
}

// Metinler yüklenmeden başlama: önce dil dosyası, hata olsa da sayfa çalışsın
fetch(`/locales/${LANG}.json`).then((r) => r.json()).then((j) => { T = j; }).catch(() => {}).finally(start);
