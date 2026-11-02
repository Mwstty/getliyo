; Inno Setup betiği. Önce scripts\build.bat ile dist\ altında üç EXE üretilmiş olmalı:
; getliyo.exe, getliyo-host.exe, getliyo-eklenti-kayit.exe
#define MyAppName "getliyo"
#define MyAppExe "getliyo.exe"
#define MyHostExe "getliyo-host.exe"
#define MyRegExe "getliyo-eklenti-kayit.exe"
#define MyAppVersion "1.2.0"

[Setup]
AppId={{B7C1F3A2-5D6E-4E0A-9C11-3F2A8D6E7B10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppName}
DefaultDirName={autopf}\getliyo
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\Output
OutputBaseFilename=getliyo-setup
SetupIconFile=..\resources\icon.ico
UninstallDisplayIcon={app}\{#MyAppExe}
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
; HKCU altına yazılıyor (native messaging kaydı dahil) -> yönetici izni gerekmez.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

; Kurulum sihirbazı, hangi parçaların kurulacağını soran bir seçim ekranı gösterir:
; "Tam kurulum" (hepsi), "Sadece uygulama" (tarayıcı eklentisi köprüsü olmadan) ya da
; kullanıcının kendi seçtiği bileşenler. Ana uygulama (Flags: fixed) her zaman kurulur.
[Types]
Name: "full"; Description: "Tam kurulum (önerilir)"
Name: "compact"; Description: "Sadece uygulama (tarayıcı eklentisi olmadan)"
Name: "custom"; Description: "Özel seçim"; Flags: iscustom

[Components]
Name: "app"; Description: "getliyo (ana uygulama)"; Types: full compact custom; Flags: fixed
Name: "browserext"; Description: "Tarayıcı eklentisi desteği (sağ tık ile indirme köprüsü)"; Types: full custom

; Kurulum sihirbazında kullanıcıya sorulan onay kutuları. Her biri isteğe bağlı,
; varsayılan değerleri (checked/unchecked) makul seçilmiştir.
[Tasks]
Name: "desktopicon"; Description: "Masaüstüne kısayol oluştur"; GroupDescription: "Kısayollar:"; Flags: checkedonce
Name: "startup"; Description: "Windows açılışında otomatik başlat"; GroupDescription: "Başlangıç:"; Flags: unchecked
Name: "openguide"; Description: "Kurulum bitince kullanım kılavuzunu göster"; GroupDescription: "Kurulum sonrası:"; Flags: checkedonce

[Files]
Source: "..\dist\{#MyAppExe}"; DestDir: "{app}"; Flags: ignoreversion; Components: app
Source: "..\dist\{#MyHostExe}"; DestDir: "{app}"; Flags: ignoreversion; Components: browserext
Source: "..\dist\{#MyRegExe}"; DestDir: "{app}"; Flags: ignoreversion; Components: browserext
Source: "..\bin\*"; DestDir: "{app}\bin"; Flags: ignoreversion recursesubdirs; Excludes: ".gitkeep"; Components: app
Source: "..\browser-extension\*"; DestDir: "{app}\browser-extension"; Flags: ignoreversion recursesubdirs; Components: browserext
Source: "OKUBENI.txt"; DestDir: "{app}"; Flags: ignoreversion; Components: app
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion; Components: app

; Başlat menüsü kısayolları HER ZAMAN oluşturulur (aranınca çıkması için) -- opsiyonel olan
; yalnızca masaüstü kısayolu, otomatik başlatma ve kılavuzu gösterme.
[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Components: app
Name: "{group}\Tarayıcı Eklentisini Kaydet"; Filename: "{app}\{#MyRegExe}"; Components: browserext
Name: "{group}\Kullanım Kılavuzu"; Filename: "{app}\OKUBENI.txt"; Components: app
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon; Components: app
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: startup; Components: app

[Run]
Filename: "{app}\OKUBENI.txt"; Description: "Kullanım kılavuzunu göster"; Flags: postinstall shellexec skipifsilent; Tasks: openguide
Filename: "{app}\{#MyAppExe}"; Description: "{#MyAppName} uygulamasını başlat"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\bin"

; Kaldırma sırasında SADECE uygulamanın kendi kayıtlarını temizler:
;  - Tarayıcı eklentisi Native Messaging kayıtları (Chrome/Edge, HKCU — başka programlara dokunmaz)
;  - Kullanıcının seçtiği veri kategorileri (ayarlar/geçmiş/önbellek/loglar/indirilen dosyalar),
;    özel kaldırma ekranındaki onayına göre. Varsayılan: HİÇBİRİ silinmez, veri korunur (madde 57).
[UninstallRun]
Filename: "reg.exe"; Parameters: "delete ""HKCU\Software\Google\Chrome\NativeMessagingHosts\com.getliyo.app"" /f"; Flags: runhidden; RunOnceId: "RemoveChromeNMH"
Filename: "reg.exe"; Parameters: "delete ""HKCU\Software\Microsoft\Edge\NativeMessagingHosts\com.getliyo.app"" /f"; Flags: runhidden; RunOnceId: "RemoveEdgeNMH"
Filename: "{app}\{#MyAppExe}"; Parameters: "--uninstall-cleanup {code:GetCleanupArgs}"; Flags: runhidden waituntilterminated skipifdoesntexist; Check: HasAnyCleanupSelected

[Code]
var
  CbSettings, CbHistory, CbCache, CbLogs, CbDownloads: TNewCheckBox;
  CleanSettings, CleanHistory, CleanCache, CleanLogs, CleanDownloads: Boolean;

function HasAnyCleanupSelected(): Boolean;
begin
  Result := CleanSettings or CleanHistory or CleanCache or CleanLogs or CleanDownloads;
end;

function GetCleanupArgs(Param: String): String;
var
  Args: String;
begin
  Args := '';
  if CleanSettings then Args := Args + ' --settings';
  if CleanHistory then Args := Args + ' --history';
  if CleanCache then Args := Args + ' --cache';
  if CleanLogs then Args := Args + ' --logs';
  if CleanDownloads then Args := Args + ' --downloads';
  Result := Trim(Args);
end;

// Kaldırma başlamadan önce: kullanıcıya hangi verilerin de silinmesini istediğini sorar.
// Varsayılan (hiçbiri işaretlenmemiş): sadece program dosyaları kaldırılır, TÜM kullanıcı
// verisi (ayarlar, geçmiş, indirilen dosyalar) korunur.
function InitializeUninstall(): Boolean;
begin
  CleanSettings := MsgBox('Uygulama ayarları da silinsin mi?', mbConfirmation, MB_YESNO) = IDYES;
  CleanHistory := MsgBox('İndirme geçmişi (veritabanı) da silinsin mi?', mbConfirmation, MB_YESNO) = IDYES;
  CleanCache := MsgBox('Önbellek (küçük resim önbelleği) da silinsin mi?', mbConfirmation, MB_YESNO) = IDYES;
  CleanLogs := MsgBox('Log dosyaları da silinsin mi?', mbConfirmation, MB_YESNO) = IDYES;
  CleanDownloads := MsgBox('Uygulamanın indirdiği dosyalar da silinsin mi? (GERİ ALINAMAZ)', mbConfirmation, MB_YESNO) = IDYES;
  Result := True;
end;
