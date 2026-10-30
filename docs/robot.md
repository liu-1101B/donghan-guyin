# 东汉古韵机器人（Jetson AGX Orin）

在 Jetson AGX Orin 上运行的语音交互机器人：
**采音 → 语音识别 → 文言文翻译与回答 → 自然语音 / 东汉古韵 双模式播放**。

不重写原项目核心：`phonology_db.py`、`sound_synth.py`、`classical_translator.py` 原样保留；
`guyun_app.py` 继续作为网页调试界面。机器人在其外层新增 `robot/`、`services/`、`language/` 三层。

## 架构

```
 USB 麦克风
      │
      ▼
 Jetson 本地录音 (arecord, 16kHz mono)
      │
      ▼
 本地语音识别 (SenseVoice / sherpa-onnx) ── Vosk 兜底，云端 ASR 接口预留
      │
      ▼
 现代汉语文本
      │
      ▼
 文言文翻译 + 回答 (language/turn_engine.py)
      │   有 API 密钥：调用配置的大模型 API；无 API：本地词典/预设应答
      │   词典未命中：只合成输入文本的古汉语翻译，不补造回答
      ▼
 语音路由 (robot/voice_router.py, m 键运行时切换)
   ┌──────────────┴──────────────┐
   ▼                             ▼
 自然语音                    东汉古韵
 Edge TTS (zh-CN-YunxiNeural)  汉字 → lookup_char() → IPA
 → MP3                          → synthesize_text() → WAV
   └──────────────┬──────────────┘
                  ▼
          Linux: PipeWire 默认输出；Windows: sounddevice/PortAudio 系统设备
```

## 环境（本机已验证）

- Jetson AGX Orin, L4T R39.2.1 (JetPack 6.x), Ubuntu 24.04, Python 3.12, aarch64
- USB 音频一体机：card 2（采集 + 播放），`plughw:2,0`
  - **注意**：该 USB 3合1 耳机的喇叭侧若未接设备，则 `plughw:2,0` 输出无声（物理未接）。
  - 麦克风侧接好即可采集（`arecord -D plughw:2,0`）。
- 扬声器：蓝牙音箱（PipeWire 默认输出自动跟随），或把耳机插到 USB 一体机
- 麦克风/扬声器权限：用户需在 `audio` 组（本机 lab006 已是）

## Windows 10/11 运行

Windows 使用原生音频后端（`sounddevice/PortAudio`），不需要安装 `arecord`、`pw-play` 或 `wpctl`。在仓库根目录双击 `start.bat` 即可创建虚拟环境、安装依赖并启动新版机器人界面 `robot/app.py`。

- 首次启动可选择下载 SenseVoice 多语识别模型（约 228 MB，来自 hf-mirror），下载后路径应为 `models/sense-voice/`（`model.int8.onnx` + `tokens.txt`）。未安装模型时，文字输入与语音合成功能仍可用，语音输入不可用。旧的 Vosk 小模型（44 MB，`models/vosk-small-cn/`）仍可作为兜底，但识别精度明显更差。
- 音频设备默认跟随 Windows 系统默认麦克风和扬声器；左侧「播放设备」可以选择特定输出设备（同名设备会带 ` · #序号` 以便区分）。
- **语音输入是「按住说话、松开发送」**：麦克风在浏览器侧采集（不占用服务器的录音设备），松手后本地 SenseVoice 识别并回填输入框（自带标点）。因为浏览器只在 `http://localhost`（或 https）下允许开麦克风，用局域网 IP 打开时语音输入会被拦，此时用文字输入即可。
- 每次录音后界面会留一行状态：`已录 2.2 秒（峰值 -14 dBFS / 均方根 -27 dBFS）· 识别：…`。识别为空时先看这两个数字：峰值低于 -45 dBFS 说明麦克风没收到声音（查默认输入设备与浏览器权限）；数值正常却没字，是小模型能力问题，靠近麦克风、说慢一点再试。
- 对话模式只有两种：**大模型 API** 和**本地词典**。密钥可以直接在界面左侧「大模型 API 设置」里填写（写入本机 `.env`，立即生效），不必手动改文件。这一版不再连接 `127.0.0.1:8080` 的本地模型服务；没有密钥时请用本地词典模式。
- 界面固定使用浅色「宣纸」主题（`.streamlit/config.toml` 里 `base = "light"`），系统/浏览器切深色模式也不会变成浅字压浅底。
- Edge TTS 自然语音需要联网；古韵合成使用本地音韵库。
- 如只需要独立合成器旧界面，请启动 `start_synthesizer.bat`，它运行的是 `guyun_app.py`，不是机器人界面。

若 Windows 录音/播放失败，请先检查 Windows「声音设置」中默认输入/输出设备，再确认 `sounddevice` 已安装。Linux/Jetson 的 PipeWire/ALSA 逻辑保持不变。

## 两种对话模式

机器人仅有两种对话模式，可在网页左侧「对话模式」入口切换：

- **大模型 API（高质量回答）**：在网页左侧「大模型 API 设置」里填接口地址、模型名和密钥，点「保存」即时生效（内容写入本机 `.env`）。也可以手动把 `.env.example` 复制为 `.env` 再填。
- **本地词典（简单回复）**：完全不调用模型 API。词典匹配成功则使用预设文言应答；没有匹配项时不输出虚构回答，只将输入文本按本地字典转写为古汉语并播放。

首次启动时，若环境里已有 API 密钥，默认选择 API 模式；否则默认选择本地词典模式。模式存于仓库根目录的 `.robot_preferences.json`，此文件已加入 `.gitignore`，再次启动会沿用上次选择。运行中切换会立即保存。

若用户选择 API 模式却未配置密钥，程序会提示并暂用本地词典，不会尝试本地部署模型。API 请求失败时也回退到词典；若词典未命中，则只播放古汉语翻译。密钥只保存在本机 `.env` 中（界面里「清除密钥」可一键清空），勿提交至版本库。API 模式会将输入及近期对话上下文发送给 API 服务商。

## 安装

```bash
# 系统工具（需要 root；本沙箱无法 sudo，请在开发板终端执行）
sudo apt install -y alsa-utils ffmpeg   # espeak-ng 可选（缺失时自动用共振峰回退）

cd donghan-guyun
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-robot.txt

# 下载 SenseVoice 识别模型（约 228MB）到 models/sense-voice/
mkdir -p models/sense-voice
B=https://hf-mirror.com/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/resolve/main
curl -L -o models/sense-voice/model.int8.onnx "$B/model.int8.onnx"
curl -L -o models/sense-voice/tokens.txt      "$B/tokens.txt"

# （可选）旧方案：Vosk 小模型 44MB，精度更差，只在没有上面那套时兜底
# mkdir -p models && cd models
# curl -O https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip
# python3 -c "import zipfile,os; z=zipfile.ZipFile('vosk-model-small-cn-0.22.zip'); z.extractall(); os.rename('vosk-model-small-cn-0.22','vosk-small-cn')"
```

## 运行

```bash
source .venv/bin/activate

# 1) 链路自检（录 2 秒回放 + 识别基准 + 双模式合成播放）
python -m robot.main --selftest

# 2) 交互模式（按键说话）
python -m robot.main                # 默认自然语音
python -m robot.main --mode ancient # 默认东汉古韵

# 3) 免麦克风测试
python -m robot.main --text "今天天气真好"

# 4) 网页使用界面（推荐，风格对齐原项目 guyun_app.py）
streamlit run robot/app.py
#   浏览器打开 http://localhost:8501
#   功能：文字输入 / 按住说话、双模式、音色+语速+基频滑杆、
#         浏览器内播放 / 一键"设备播放"（走 PipeWire 蓝牙，后台不阻塞）、
#         扩展朗读：🗣 回答·现代汉语读 / 📜 我的话·古汉语翻译读、
#         IPA 与逐字音韵表、多轮历史
```

交互键位：

| 按键 | 功能 |
|---|---|
| 空行 (Enter) | 录音（命令行版仍然是固定 5 秒） |
| 直接输入文字 | 免麦克风，直接处理 |
| `m` | 切换 自然语音 / 东汉古韵（无需重启） |
| `r` | 重播上一条回答 |
| `c` | 清空对话历史 |
| `q` | 退出 |

## 蓝牙音箱输出（本机已验证）

播放通道走 **PipeWire 默认输出**（`pw-play`），所以只要蓝牙音箱是当前
默认 sink，机器人所有声音都会自动从音箱出来；`aplay` 直连仅作回退。

### 一次性配对（已完成）

```bash
bluetoothctl
  scan on                      # 音箱先开配对模式(灯快闪)
  pair <MAC>                   # 本机音箱: F8:D3:F0:A9:08:68 (Relink脑机接口)
  trust <MAC>
  connect <MAC>
  quit
```

### 每次开机/重启后

```bash
./robot/bt_connect.sh          # 连接 + 设为默认输出 + 音量过低时抬到 60%
```

### ⚠️ NVIDIA Jetson 关键坑：蓝牙 A2DP 被官方禁用

JetPack 的 `/usr/lib/systemd/system/bluetooth.service.d/nv-bluetooth-service.conf`
用 `--noplugin=audio,a2dp,avrcp,sap` 把蓝牙音频插件整个禁了，导致**能配对、
能连接、但永远不出声**（`journalctl -u bluetooth` 可见
`Excluding (cli) a2dp`）。已用 override 修复：

```
/etc/systemd/system/bluetooth.service.d/zz-restore-a2dp.conf
    ExecStart=
    ExecStart=/usr/libexec/bluetooth/bluetoothd -d --noplugin=audio,sap
```

（只保留禁用 HFP 音频与 SAP；A2DP/AVRCP 重新启用。NVIDIA 原文件保留在系统路径 `/usr/lib/systemd/system/bluetooth.service.d/nv-bluetooth-service.conf` 未改动，本地副本备份为 `nv-bluetooth-service.conf.bak`。）若系统升级覆盖，需重跑
`sudo systemctl daemon-reload && sudo systemctl restart bluetooth`。

### 排查口诀（无声时按顺序查）

1. `wpctl status` → 蓝牙 sink 在不在、是不是 `*` 默认、`[vol:]` 是否 > 0
2. `bluetoothctl info <MAC>` → `Connected: yes`？
3. `journalctl -u bluetooth | grep -i a2dp` → 有没有 `Excluding (cli) a2dp`
4. `pw-play audio_out/tone440.wav` → 直接听测试音，隔离上层代码
5. **A2DP 假连接**：显示 Connected 但 `pw-play` 卡住不返回（3 秒的音
   等 30 秒不放完）→ 通道挂死了，跑 `./robot/bt_reset.sh` 强制断连重连即可

### A2DP 假连接（已遇到并根治）

现象：蓝牙显示已连接、sink 也是默认，但音频流通道实际已挂起：
`pw-play` 一直阻塞不返回（3 秒的音等 30 秒不放完），音箱完全没声。

**故障模式（2026-10-25 逐一定位）**：

1. **WirePlumber 自动挂起 → A2DP 重协商卡死**（主因）：
   `suspend-node.lua` 把空闲 >5s 的音频节点挂起；Jetson 上 A2DP 重新
   协商经常卡死（"假连接"：`pw-play` 永久阻塞或音箱无声）。
2. **A2DP profile 静默断开**：bluez 日志 `a2dp-sink: connected ->
   disconnected` 而 L2CAP 仍在 → PipeWire 蓝牙 sink 消失 → 默认输出掉回
   **无喇叭的空接口** → `pw-play` 不报错但全程无声。
3. **持续静音流"保活"——失败**：该音箱（Relink）约 1.5 分钟后主动断开
   A2DP profile，保活反而加速故障。已放弃。

**根治（系统级，已验证）**：禁用蓝牙输出节点的自动挂起——
`/etc/xdg/wireplumber/wireplumber.conf`：

```
wireplumber.rules = [
  { matches = [ { node.name = "bluez_output.*" } ]
    actions.update-props = { "session.suspend-timeout-seconds" = 0 } }
]
```

`systemctl --user restart wireplumber` 生效。验证：节点空闲 15s/90s
（原 5s 阈值倍数）后通道仍活。**系统升级/重装 wireplumber 后需重建
此文件**（内容即上方规则）。

**兜底（应用级）**：界面播放按钮播放前三重检查
（`robot/audio_io.py::bt_status()` + `AudioIO.probe()`）：
A2DP sink 存在 + 是默认输出 + 0.3s 探测音播得通。任一失败 → 自动
`./robot/bt_reset.sh`（断开→重连→**显式 `wpctl set-default`**→3s
测试音自检）→ 复检后再播。正常时开销约 2.5s，异常时约 20s。

手动恢复（界面外的终端里）：

```bash
./robot/bt_reset.sh
```

## 目录结构（新增部分）

```
robot/
├── main.py          # 主循环（按键说话 / selftest / text 模式）
├── app.py           # Streamlit 网页界面（音色/语速/基频滑杆，推荐入口）
├── audio_io.py      # arecord 采音 + 播放（pw-play 优先走默认输出, aplay 回退；MP3 经 miniaudio 解码）
│                    #   含通道探测 probe() 与蓝牙状态快照 bt_status()
├── bt_connect.sh    # 蓝牙音箱：连接 + 设为默认输出 + 音量校正
├── bt_reset.sh      # A2DP 恢复：断开→重连→设默认输出→测试音自检
├── session.py       # 多轮对话状态（默认保留 8 轮）
└── voice_router.py  # 自然语音 / 东汉古韵 运行时切换（持有音色/语速参数）

services/
├── asr_client.py    # 本地识别：SenseVoice/Paraformer(sherpa-onnx) → Vosk 兜底；自动重采样
├── llm_client.py    # 翻译+回答：OpenAI 兼容接口可选，本地词典/规则回退
└── tts_client.py    # Edge TTS 自然语音（自动尝试代理→直连）

language/
├── turn_engine.py   # 单轮统一处理：文本进 → 音频出（含双路回退）
├── style_prompt.py  # 古汉语风格提示词与长度限制
└── ancient_tts.py   # 汉字 → 东汉 IPA → WAV（含覆盖率统计）

config/settings.yaml # 音频设备、对话容量、默认模式
.env.example         # 可选云端密钥模板（复制为 .env）
```

## 接口一览（与方案文档一致）

| 接口 | 位置 | 输入 | 输出 |
|---|---|---|---|
| `record()` | robot/audio_io.py | 时长 | WAV 文件 |
| `transcribe_wav()` | services/asr_client.py | WAV | 现代汉语文本 |
| `generate_turn()` | services/llm_client.py | 文本+历史 | `{translation, reply}` |
| `speak_natural(text, voice, rate)` | services/tts_client.py | 文本+音色+语速 | MP3 字节 |
| `synthesize_ancient(text, pitch, speed)` | language/ancient_tts.py | 文本+基频+语速 | (WAV 字节, 覆盖率) |
| `play_wav()/play_async()` | robot/audio_io.py | 字节 | 播放状态（async 后台不阻塞） |
| `probe(timeout=6)` | robot/audio_io.py | — | 通道是否活着（False=假连接） |
| `bt_status(mac)` | robot/audio_io.py | — | 蓝牙快照 `{connected, sink_id, sink_name, is_default}` |

## 关于"东汉古韵"的说明

古韵模式是**音韵学近似复原**：查东汉音韵库（当前约 703 字）得到重构 IPA，
再用 eSpeak-ng/共振峰合成。它不是历史录音级别的还原。
每轮会报告覆盖率（已收录字数 / 总字数）；未收录字走现代拼音近似，
提示词已限制模型少用生僻字、控制回复长度。

## 已知限制与后续

- 当前网络环境 DNS/代理不稳定：Edge TTS 自动在"代理→直连"间回退；断网时自然语音自动回退本地古韵合成。
- 识别后端按可用性自动选：SenseVoice（默认，中文准确率高、带标点、5 秒语音约 0.1 秒解完）> Paraformer > Vosk 小模型（精度弱，仅兜底）。想继续提升可换更大的 SenseVoice/FunASR 模型或接云端 ASR。
- 播放通道：`pw-play` 优先（走 PipeWire 默认输出，自动跟随当前设备，如蓝牙音箱），
  回退 `aplay -D plughw:2,0` 直连。想换音箱/耳机只需 `wpctl set-default <sink>`，
  或用 `./robot/bt_connect.sh`，无需改代码。
- 本机唯一"内置扬声器"是 USB 耳麦（card 2，GeneralPlus 三合一：麦+喇叭+线控），
  但其喇叭侧未接线时 `plughw:2,0` 无声（物理未接）；HDMI 显示器无内置喇叭
  （EDID 无音频位）。外放已接蓝牙音箱（见上一节）。
- 后续：唤醒词、播放打断、超时与联网失败提示、开机自启（bt_connect.sh + 主程序）。
