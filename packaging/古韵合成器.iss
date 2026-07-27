; 古韵合成器 Inno Setup 安装脚本
; 生成单文件安装包，用户双击安装即可使用

#define MyAppName "古韵合成器"
#define MyAppVersion "2.0"
#define MyAppPublisher "GuYun"
#define MyAppURL "https://github.com/gu-yun"
#define MyAppExeName "古韵合成器.exe"

[Setup]
AppId={{B8F4A3D2-7E6C-4A1F-9D5B-C2E8F0A6D9B4}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=.
OutputBaseFilename=古韵合成器_Setup_v{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
DisableProgramGroupPage=yes

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标:"

[Files]
; PyInstaller 打包输出（所有文件递归复制）
Source: "dist\古韵合成器\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{app}\启动古韵合成器"; Filename: "{app}\启动.bat"; WorkingDir: "{app}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
; 清理 Streamlit 运行时缓存
Type: filesandordirs; Name: "{app}\.streamlit"
Type: filesandordirs; Name: "{userappdata}\streamlit"
