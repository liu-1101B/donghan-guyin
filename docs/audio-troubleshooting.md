# 音频问题交接文档（2026-10-25）

> 目的：本机 Jetson 上蓝牙音箱播放反复"无声"，已多次修复仍未稳定。
> 请基于以下事实排查，**不要重复已验证失败的方案**。

## 1. 环境

| 项 | 值 |
|---|---|
| 硬件 | Jetson AGX Orin |
| 系统 | L4T R39.2.1 (JetPack 6.x), Ubuntu 24.04, aarch64 |
| Python | 3.12.3，项目 venv `.venv` |
| 音频栈 | PipeWire + **WirePlumber 0.4.17**（用户级服务 `wireplumber.service`）+ bluez |
| 代码 | `/home/lab006/.dsh/ungrouped/deepdive/donghan-guyin`（git: liu-1101B/donghan-guyin） |
| 界面 | Streamlit `robot/app.py`，端口 8501 |
| 本地 LLM | llama-server `127.0.0.1:8080`（Qwen3-30B-A3B gguf） |
| TTS | Edge TTS（代理 `127.0.0.1:7897` 不稳定，有直连回退） |

## 2. 音频设备拓扑（关键）

- **麦克风**：USB 三合一耳麦（card 2），`arecord -D plughw:2,0`，**工作正常**。
- **外放目标**：蓝牙设备 **"Relink脑机接口"**，MAC `F8:D3:F0:A9:08:68`，
  A2DP Sink（PipeWire 节点名 `bluez_output.F8_D3_F0_A9_08_68.*`，
  sink 名称在 `Relink脑机接口 - Find My` / `Relink脑机接口` 之间变过，**id 也频繁变**：90→94→79→39）。
  ⚠️ 从名字看这**可能是耳机/头戴设备而非音箱**，这类设备空闲时主动拆 A2DP 的倾向很强。
- **无喇叭的"默认陷阱"**：`Built-in Audio Analog Stereo`（sink 33，3.5mm 口）
  物理上没接喇叭。蓝牙 sink 一消失，PipeWire 默认输出就掉到这里，
  `pw-play` 返回成功但**全程无声**——这是多次"没声音"的表象。
- HDMI 显示口无音频；无其它可用喇叭。

## 3. 已修好且稳定的部分

1. **JetPack 的 bluetoothd 禁 A2DP bug（已修）**：
   NVIDIA 默认 drop-in `/usr/lib/systemd/system/bluetooth.service.d/nv-bluetooth-service.conf`
   用 `--noplugin=audio,a2dp,avrcp,sap` 启动 bluetoothd → A2DP 永不激活。
   已用 sudo 覆盖 `/etc/systemd/system/bluetooth.service.d/zz-restore-a2dp.conf`：
   ```
   ExecStart=
   ExecStart=/usr/libexec/bluetooth/bluetoothd -d --noplugin=audio,sap
   ```
   此后 A2DP sink 能出现、测试音**用户亲耳听到过多次**（"能听见"）。
   备份 `nv-bluetooth-service.conf.bak` 在仓库根目录。
2. 蓝牙配对/连接/重连脚本：`robot/bt_connect.sh`、`robot/bt_reset.sh`
   （断开→重连→`wpctl set-default`→3s 测试音自检）。
3. 应用层：`robot/audio_io.py` 有 `probe()`（0.3s 探测音）、
   `bt_status()`（解析 `bluetoothctl info` + `wpctl status` Sinks 区块）；
   `robot/app.py` 播放按钮三重检查（sink 存在 + 是默认 + probe），
   失败自动跑 `bt_reset.sh` 再复检。
4. 录制、ASR（Vosk）、LLM、TTS 合成本身都正常。

## 4. 反复出现的故障（未解决）

**现象**：播放一段成功后，**空闲数分钟再播就没声音**；有时 `pw-play` 卡死
（3 秒的音等 30 秒不返回），有时直接"成功"但无声。

**bluez 日志证据**（`journalctl -u bluetooth`）：
```
16:40:56 a2dp-sink state changed: connected -> disconnected   ← 保活静音流启动后 ~1.5min
16:59:07 a2dp-sink state changed: connected -> disconnected
16:59:22 a2dp-sink state changed: disconnected -> connecting -> connected
```
即 **A2DP 音频 profile 反复断开，而 L2CAP 连接保持 `Connected: yes`**。
断开后 PipeWire 蓝牙 sink 消失 → 默认输出掉到空 3.5mm 口 → 无声。

## 5. 已尝试过的方案与结论（勿重复）

| 方案 | 结果 |
|---|---|
| 断开重连（bt_reset.sh） | 每次都能临时恢复（测试音 rc=0），但几分钟后复现 |
| 持续静音流"保活"（pw-play 喂 16kHz 静音） | **失败**：音箱 ~1.5min 后主动断开 A2DP，加速故障。已撤销 |
| WirePlumber 规则禁用蓝牙输出节点自动挂起<br>`/etc/xdg/wireplumber/wireplumber.conf`：<br>`{ matches=[{node.name="bluez_output.*"}], actions.update-props={"session.suspend-timeout-seconds"=0} }` + `systemctl --user restart wireplumber` | 15s/90s 空闲浸泡测试通过（sink 在、是默认、probe 通），**但用户 ~6 分钟后仍报无声** → 不足以根治，说明断流不完全来自本机挂起策略 |

## 5b. 2026-10-26 取证进展（重要新证据）

**设备身份确认**：`bluetoothctl info` 显示
`Icon: audio-headphones`、`Modalias: bluetooth:v004Cp2027d215C`
——这是**头戴耳机**（v004C 是 Apple 厂商号，兼容 AirPods 协议类设备）。
此类设备空闲主动休眠/断开 A2DP 是正常设计行为。

**昨晚全部断开事件已逐条归因**（`journalctl -u bluetooth`）：

| 时间 (10-25) | 事件 | 归因 |
|---|---|---|
| 15:46 / 15:58 | a2dp-sink disconnecting + `dev_disconnected reason 2` (Remote) | **bt_reset.sh 人为操作** |
| 16:39:42 | 静音保活流启动（A2DP ACTIVE Playing=1） | 实验开始 |
| **16:40:56** | **链路直断 `reason 3` (Supervision Timeout)**，AVDTP `connection_lost`，A2DP 1 分钟内死 | **保活静音流害的**——设备收到持续异常静音流后断链 |
| 16:54 / 16:59 / 17:07 | reason 2 | **bt_reset.sh 人为操作** |
| 17:30 | reason 2 | 收尾断开 |

**关键结论**：
1. 日志里**没有**任何"空闲中设备自己悄悄断 A2DP profile"的记录
   ——昨晚的"无声"实际来自两个已定位机制：
   - **WirePlumber 自动挂起 → 通道卡死**（15:44、17:06 两次，
     profile 全程 connected，`pw-play` 卡 8 秒不返回）；
   - **保活静音流杀链**（16:40 一次）。
   两者均已处理：wireplumber 禁挂起规则生效中 + 保活已撤销。
2. Jetson 曾整夜睡眠：今早 `adapter-not-powered`（适配器掉电），
   唤醒后设备自动重连成功。**说明夜间断开也是 Jetson 睡眠所为，
   不是设备自己断。**
3. **13 分钟纯空闲观察窗结果（10-26 13:22–13:35，零故障）**：
   修正后的 `robot/monitor_a2dp.sh`（每 10s 只读状态检查，每 60s
   一次 3s 探测音）52 轮全绿，8 次真实探测音全部播通；
   bluez 日志显示窗口内只有 wireplumber（bus owner :1.37382）
   正常的 Acquire/Release 循环，**无 link loss、无 reason 码、
   无设备侧断开**。→ 当前配置（禁挂起+无保活+三重检查兜底）
   下至少 13 分钟尺度内问题不再复现。
4. 注意：10-25 17:06 用户报"没声音"发生在 wireplumber 规则
   生效后 ~6 分钟（probe=False 卡死型），随后 bt_reset 恢复、
   之后直到 Jetson 睡眠（17:30）再未复现——可能是 wireplumber
   重启后节点的遗留状态。若再遇卡死型，`bt_reset.sh` 可 20s 内恢复。
5. 设备侧嫌疑（耳机主动睡 A2DP）在现有日志中**没有证据**：
   所有链路断开都有明确归因（人为重置或保活静音流）。
   手机抢占也未能证实（观察窗内无外源干扰）。

## 6. 当前精确状态（交给下家的起点）

- bluetoothd 覆盖配置**已生效**（A2DP 可建立）。
- wireplumber 禁挂起规则**已生效**（17:00 左右 90s 浸泡通过）。
- 最近一次用户报"还是不行"（~17:06），当时 `bt_status` 显示
  `connected=True, sink_id=94, is_default=True` 但 **`probe=False`**
  （通道挂死型，非 sink 消失型）→ 当时跑了 bt_reset.sh 恢复（rc=0）。
- 之后又加了 wireplumber 规则 + 重启（sink id 变为 39，名称失去 ` - Find My` 后缀）。
- **未解决**：空闲后 A2DP 仍会死，且死法有两种（sink 消失 / 通道卡死）。

## 7. 待排查方向（给接手者的线索）

1. **断开是谁发起的**：`a2dp-sink: connected -> disconnected` 之前几行
   `journalctl -u bluetooth` 看是 `policy_disconnect`（本机策略）还是
   设备侧断（如 `link lost`/`timeout`/`remote`）；必要时
   `hcitool`/`btmon` 抓 HCI 层看是设备主动 `Disconnection Complete`。
2. **设备侧嫌疑最大**：Relink"脑机接口"（疑似耳机/头戴）空闲主动睡 A2DP。
   可换一台普通蓝牙音箱做对照实验；或查该设备是否同时被手机抢占
   （手机连上时会把 Jetson 挤掉）。
3. **A2DP 重协商卡死**（probe 超时型）：查 `wpctl inspect <sink>` 节点状态、
   PipeWire 侧 `pw-top`/journal，是否有 SBC/codec 协商问题；
   可试强制 codec（`bluez5` 的 `codec` 属性，或 PipeWire 属性 `media.name`）。
4. **确认"无声"的物理侧**：让用户在 Jetson 上直接
   `pw-play audio_out/tone440.wav` 时**贴近设备听**，并检查设备实体音量/静音；
   排除"其实有声但太小/设备静音"的可能。
5. 注意 sink id/名称会变，任何硬编码 id 的方案都会失效；
   按 MAC/名称匹配（名称可能带 ` - Find My` 后缀，用"包含"匹配）。

## 8. 常用命令速查

```bash
bluetoothctl info F8:D3:F0:A9:08:68          # L2CAP 连接状态
wpctl status | sed -n '/Sinks:/,/Sink endpoints/p'   # 默认输出(*)是谁
journalctl -u bluetooth --since "10 min ago" | grep "a2dp-sink state changed"
./robot/bt_reset.sh                           # 断开→重连→设默认→测试音
pw-play audio_out/tone440.wav                 # 3s 测试音(卡住=通道死)
systemctl --user status wireplumber
sudo systemctl status bluetooth
```

## 9. 代码位置

- `robot/app.py` — Streamlit 界面 + 播放三重检查 `_ensure_playable`
- `robot/audio_io.py` — `probe()` / `bt_status()` / 播放（pw-play 优先，aplay 回退）
- `robot/bt_reset.sh` — A2DP 重置脚本
- `robot/monitor_a2dp.sh` — 取证监视器（10s 只读状态检查 + 60s 探测音，
  故障自动抓快照不恢复；日志 `~/a2dp_monitor.log`，快照 `~/a2dp_fault_snapshot/`）
- [docs/robot.md](robot.md) — 完整排障史（"A2DP 假连接"一节）
