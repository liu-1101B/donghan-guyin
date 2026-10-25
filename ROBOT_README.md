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
      │   默认本地回退：词典翻译 + 规则应答
      │   配置 LLM_API_KEY 后走 OpenAI 兼容接口
      ▼
 语音路由 (robot/voice_router.py, m 键运行时切换)
   ┌──────────────┴──────────────┐
   ▼                             ▼
 自然语音                    东汉古音
 Edge TTS (zh-CN-YunxiNeural)  汉字 → lookup_char() → IPA
 → MP3                          → synthesize_text() → WAV
   └──────────────┬──────────────┘
                  ▼
          USB 有源扬声器 (aplay)
```

## 环境（本机已验证）

- Jetson AGX Orin, L4T R39.2.1 (JetPack 6.x), Ubuntu 24.04, Python 3.12, aarch64
- USB 音频一体机：card 2（采集 + 播放），`plughw:2,0`
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

## 目录结构（新增部分）

```
robot/
├── main.py          # 主循环（按键说话 / selftest / text 模式）
├── audio_io.py      # arecord 采音 + aplay 播放（MP3 经 miniaudio 解码）
├── session.py       # 多轮对话状态（默认保留 8 轮）
└── voice_router.py  # 自然语音 / 东汉古音 运行时切换

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
| `speak_natural()` | services/tts_client.py | 文本 | MP3 字节 |
| `synthesize_ancient()` | language/ancient_tts.py | 文本 | (WAV 字节, 覆盖率) |
| `play_wav()/play_mp3()` | robot/audio_io.py | 字节 | 播放状态 |

## 关于"东汉古音"的说明

古音模式是**音韵学近似复原**：查东汉音韵库（当前约 703 字）得到重构 IPA，
再用 eSpeak-ng/共振峰合成。它不是历史录音级别的还原。
每轮会报告覆盖率（已收录字数 / 总字数）；未收录字走现代拼音近似，
提示词已限制模型少用生僻字、控制回复长度。

## 已知限制与后续

- 当前网络环境 DNS/代理不稳定：Edge TTS 自动在"代理→直连"间回退；断网时自然语音自动回退本地古音合成。
- 小模型 Vosk 词汇有限，识别偶有错字（"天朗气清"→"天冷起清"）；后续可换 vosk 大模型或云端 ASR。
- eSpeak-ng 未安装（需 sudo）：古音合成自动走共振峰回退，音质一般但可运行。
- 后续：唤醒词、播放打断、超时与联网失败提示、开机自启。
