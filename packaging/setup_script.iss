; 古韵合成器 Inno Setup 安装脚本
; 使用方法：用 Inno Setup Compiler 打开此文件，点击 Build → Compile

#define MyAppName "古韵合成器"
#define MyAppVersion "3.0.0"
#define MyAppPublisher "古韵项目"
#define MyAppURL "https://github.com/your/project"
#define MyAppExeName "古韵合成器.exe"

[Setup]
; 应用信息
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; 输出配置
OutputDir=.
OutputBaseFilename=古韵合成器_Setup_v{#MyAppVersion}

; 安装目录
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes

; 压缩配置
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

; 安装包外观（无自定义图标，使用默认）
;UninstallDisplayIcon={app}\{#MyAppExeName}

; 权限（需要管理员权限写入 Program Files）
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=commandline

; 其他
DisableProgramGroupPage=yes
DisableDirPage=no
CreateAppDir=yes

[Languages]
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："; Flags: checkedonce

[Files]
; 主程序及所有依赖（递归添加整个 dist 目录）
Source: "dist\{#MyAppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; 安装完成后可选启动
Filename: "{app}\{#MyAppExeName}"; Description: "运行 {#MyAppName}"; Flags: postinstall nowait skipifsilent unchecked

[UninstallRun]
; 卸载时清理运行时生成的文件（如 eSpeak 数据）
Filename: "{cmd}"; Parameters: "/c rmdir /s /q ""{app}\_internal\espeak-ng"""; Flags: runhidden
