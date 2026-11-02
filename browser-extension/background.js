// getliyo — arka plan betiği.
// Yakaladığı URL'yi Native Messaging ile masaüstü uygulamasına iletir.
// Uygulama kapalıysa host onu başlatır; açıksa mevcut pencereye yönlendirir.

const NATIVE_HOST = "com.getliyo.app";

function notify(message) {
  chrome.notifications.create({
    type: "basic",
    iconUrl: "icons/icon128.png",
    title: "getliyo",
    message,
  });
}

function sendToApp(url) {
  if (!url || !/^https?:\/\//i.test(url)) {
    notify("Gönderilecek geçerli bir bağlantı bulunamadı.");
    return;
  }
  chrome.runtime.sendNativeMessage(NATIVE_HOST, { url }, (response) => {
    if (chrome.runtime.lastError) {
      notify(
        "Uygulamaya ulaşılamadı: " +
          chrome.runtime.lastError.message +
          "\ngetliyo kurulu ve kayıtlı mı? (scripts\\register_extension.bat)"
      );
      return;
    }
    if (response && response.ok) {
      notify("Gönderildi:\n" + url);
    } else {
      notify("Hata: " + ((response && response.error) || "bilinmeyen"));
    }
  });
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "mit-send",
    title: "getliyo ile indir",
    contexts: ["link", "video", "audio", "image", "page"],
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  const url = info.linkUrl || info.srcUrl || info.pageUrl || (tab && tab.url) || "";
  sendToApp(url);
});

// Araç çubuğu simgesine tıklama: aktif sekmenin adresini gönder.
chrome.action.onClicked.addListener((tab) => {
  sendToApp(tab && tab.url);
});
