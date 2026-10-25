# 东汉古音机器人（Jetson AGX Orin）

在 Jetson AGX Orin 上运行的语音交互机器人：
**采音 → 语音识别 → 文言文翻译与回答 → 自然语音 / 东汉古音 双模式播放**。

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
 本地语音识别 (Vosk 中文小模型)   ── 可插拔云端 ASR (services/asr_client.py)
      │
      ▼
 现代汉语文本
      │
      ▼
 文言文翻译 + 回答 (language/turn_engine.py)
      │   默认：本地 Qwen3-30B (llama-server :8080)
      │   可选：LLM_API_KEY 走 OpenAI 兼容云端；兜底：词典+规则
      ▼
 语音路由 (robot/voice_router.py, m 键运行时切换)
   ┌──────────────┴──────────────┐
   ▼                             ▼
 自然语音                    东汉古音
 Edge TTS (zh-CN-YunxiNeural)  汉字 → lookup_char() → IPA
 → MP3                          → synthesize_text() → WAV
   └──────────────┬──────────────┘
                  ▼
          PipeWire 默认输出 (pw-play: 蓝牙音箱/USB 音箱)
```

## 环境（本机已验证）

- Jetson AGX Orin, L4T R39.2.1 (JetPack 6.x), Ubuntu 24.04, Python 3.12, aarch64
- USB 音频一体机：card 2（采集 + 播放），`plughw:2,0`
  - **注意**：该 USB 3合1 耳机的喇叭侧若未接设备，则 `plughw:2,0` 输出无声（物理未接）。
  - 麦克风侧接好即可采集（`arecord -D plughw:2,0`）。
- 扬声器：蓝牙音箱（PipeWire 默认输出自动跟随），或把耳机插到 USB 一体机
- 麦克风/扬声器权限：用户需在 `audio` 组（本机 lab006 已是）

## 安装

```bash
# 系统工具（需要 root；本沙箱无法 sudo，请在开发板终端执行）
sudo apt install -y alsa-utils ffmpeg   # espeak-ng 可选（缺失时自动用共振峰回退）

cd donghan-guyin
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-robot.txt

# 下载 Vosk 中文小模型（约 44MB）到 models/
mkdir -p models && cd models
curl -O https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip
python3 -c "import zipfile,os; z=zipfile.ZipFile('vosk-model-small-cn-0.22.zip'); z.extractall(); os.rename('vosk-model-small-cn-0.22','vosk-small-cn')"
```

## 运行

```bash
source .venv/bin/activate

# 1) 链路自检（录 2 秒回放 + 识别基准 + 双模式合成播放）
python -m robot.main --selftest

# 2) 交互模式（按键说话）
python -m robot.main                # 默认自然语音
python -m robot.main --mode ancient # 默认东汉古音

# 3) 免麦克风测试
python -m robot.main --text "今天天气真好"

# 4) 网页使用界面（推荐，风格对齐原项目 guyun_app.py）
streamlit run robot/app.py
#   浏览器打开 http://localhost:8501
#   功能：文字/麦克风输入、双模式、音色+语速+基频滑杆、
#         浏览器内播放 / 一键"设备播放"（走 PipeWire 蓝牙，后台不阻塞）、
#         扩展朗读：🗣 回答·现代汉语读 / 📜 我的话·古汉语翻译读、
#         IPA 与逐字音韵表、多轮历史
```

交互键位：

| 按键 | 功能 |
|---|---|
| 空行 (Enter) | 录音 5 秒并处理 |
| 直接输入文字 | 免麦克风，直接处理 |
| `m` | 切换 自然语音 / 东汉古音（无需重启） |
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

## 目录结构（新增部分）

```
robot/
├── main.py          # 主循环（按键说话 / selftest / text 模式）
├── app.py           # Streamlit 网页界面（音色/语速/基频滑杆，推荐入口）
├── audio_io.py      # arecord 采音 + 播放（pw-play 优先走默认输出, aplay 回退；MP3 经 miniaudio 解码）
├── bt_connect.sh    # 蓝牙音箱：连接 + 设为默认输出 + 音量校正
├── session.py       # 多轮对话状态（默认保留 8 轮）
└── voice_router.py  # 自然语音 / 东汉古音 运行时切换（持有音色/语速参数）

services/
├── asr_client.py    # 本地 Vosk 识别（自动重采样/降声道），云端接口预留
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

## 关于"东汉古音"的说明

古音模式是**音韵学近似复原**：查东汉音韵库（当前约 703 字）得到重构 IPA，
再用 eSpeak-ng/共振峰合成。它不是历史录音级别的还原。
每轮会报告覆盖率（已收录字数 / 总字数）；未收录字走现代拼音近似，
提示词已限制模型少用生僻字、控制回复长度。

## 已知限制与后续

- 当前网络环境 DNS/代理不稳定：Edge TTS 自动在"代理→直连"间回退；断网时自然语音自动回退本地古音合成。
- 小模型 Vosk 词汇有限，识别偶有错字（"天朗气清"→"天冷起清"）；后续可换 vosk 大模型或云端 ASR。
- 播放通道：`pw-play` 优先（走 PipeWire 默认输出，自动跟随当前设备，如蓝牙音箱），
  回退 `aplay -D plughw:2,0` 直连。想换音箱/耳机只需 `wpctl set-default <sink>`，
  或用 `./robot/bt_connect.sh`，无需改代码。
- 本机唯一"内置扬声器"是 USB 耳麦（card 2，GeneralPlus 三合一：麦+喇叭+线控），
  但其喇叭侧未接线时 `plughw:2,0` 无声（物理未接）；HDMI 显示器无内置喇叭
  （EDID 无音频位）。外放已接蓝牙音箱（见上一节）。
- 后续：唤醒词、播放打断、超时与联网失败提示、开机自启（bt_connect.sh + 主程序）。
