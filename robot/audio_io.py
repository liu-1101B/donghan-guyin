"""
robot/audio_io.py
本地采音与播放（Jetson AGX Orin 实测可用）

- 录制：arecord（16kHz mono WAV）。
- 播放：优先 pw-play。默认输出是真实设备（蓝牙/USB/HDMI）时跟随
  默认；默认掉回 Built-in（本机无内置喇叭=无物理输出）时自动定向
  到 playback_device 配置的 sink（pw-play --target）。
  pw-play 不可用时回退 aplay 直连（playback_device 指定卡）。
  MP3/其它格式先经 miniaudio 解码为 WAV 再播。
设备按名字解析成当前卡号（USB 声卡 ALSA 卡号每次重启漂移）。
"""
import io
import os
import re
import subprocess
import tempfile
import threading
import time
import wave

try:
    import miniaudio
    MINIAUDIO_AVAILABLE = True
except ImportError:
    MINIAUDIO_AVAILABLE = False


def _pcm_to_wav(pcm: bytes, sample_rate: int, nchannels: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(nchannels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def _list_plughw(kind: str):
    """返回 [(card, device, name)]。kind='capture' 用 arecord -l，
    'playback' 用 aplay -l。ALSA 卡号每次重启/重插都会漂移，
    所以设备要按名字找，不能写死 plughw:C,D。"""
    tool = "arecord" if kind == "capture" else "aplay"
    out = subprocess.run([tool, "-l"], capture_output=True,
                         text=True).stdout
    res = []
    # arecord/aplay -l 每行形如：
    #   card 0: Device [USB Audio Device], device 0: USB Audio [USB Audio]
    # card 与 device 通常在同一行；APE 等内接口每设备一行、card 重复。
    for line in out.splitlines():
        m = re.search(r"card (\d+):[^,]*,\s*device (\d+):\s*(.+)", line)
        if not m:
            continue
        name = re.sub(r"\s*\[.*\]\s*$", "", m.group(3)).strip()
        res.append((int(m.group(1)), int(m.group(2)), name))
    return res


def _resolve_device(configured: str, kind: str) -> str:
    """把配置里的设备解析成 plughw:C,D。
    - 显式 'plughw:'/'hw:'/'plug:' 前缀 → 原样返回。
    - 否则当作设备名（子串，忽略大小写）→ 按名字找当前卡号。
    """
    if configured.startswith(("plughw:", "hw:", "plug:")):
        return configured
    for card, dev, name in _list_plughw(kind):
        if configured.lower() in name.lower():
            return f"plughw:{card},{dev}"
    return configured  # 找不到就原样，让 arecord 报错兜底


def _list_pw_sinks() -> list:
    """解析 wpctl status → [(serial, name, is_default, vol), ...]

    带音量：BT 音箱常以自己的硬件音量同步过来（可能为 0），
    此时 sink 在、通道通、pw-play 不报错，但全程无声——
    必须显式查音量才能发现。
    """
    try:
        out = subprocess.run(["wpctl", "status"], capture_output=True,
                             text=True, timeout=10).stdout
    except Exception:
        return []
    start = out.find("Sinks:")
    end = out.find("Sink endpoints", start) if start >= 0 else -1
    block = out[start:end] if start >= 0 and end > start else ""
    sinks = []
    for line in block.splitlines():
        m = re.search(r"(\*?)\s*(\d+)\.\s+(.+?)\s+\[vol:\s*([\d.]+)\]", line)
        if m:
            sinks.append((int(m.group(2)), m.group(3).strip(),
                          m.group(1) == "*", float(m.group(4))))
    return sinks


def set_pw_default(serial) -> bool:
    """把某 sink 设为 PipeWire 默认输出（wpctl set-default）。"""
    try:
        r = subprocess.run(["wpctl", "set-default", "sink",
                            str(serial)],
                           capture_output=True, text=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def _pw_node_names(mac: str) -> set:
    """pw-cli 里属性含该 MAC 的节点名集合（蓝牙 sink 精确定位用）。

    bluez A2DP sink 的 node.name 含 MAC（如 bluez_output.F8_D3_...）；
    节点显示名（如 "BS-32D"）不含 MAC，用显示名匹配会漏。
    """
    def _hex(s):  # 只留 hex，分隔符（:/-_.）不影响匹配
        return re.sub(r"[^0-9a-f]", "", s.lower())
    mac_l = _hex(mac)
    try:
        out = subprocess.run(["pw-cli", "list-objects"],
                             capture_output=True, text=True,
                             timeout=10).stdout
    except Exception:
        return set()
    names = set()
    for line in out.splitlines():
        m = re.search(r'node\.name\s*=\s*"([^"]+)"', line)
        if m and mac_l and mac_l in _hex(m.group(1)):
            names.add(m.group(1))
    return names


def _effective_sink(playback_device, target_name=None):
    """pw-play 实际会打到的 sink → (serial, name, vol) 或 None。
    有 --target 时是定向目标；否则是 PipeWire 默认 sink。"""
    target = _target_sink(playback_device, target_name)
    for s, name, is_def, vol in _list_pw_sinks():
        if target is None and is_def:
            return (s, name, vol)
        if target is not None and name == target:
            return (s, name, vol)
    return None


def set_pw_volume(serial, vol: float) -> bool:
    """设某 sink 音量（0.0~1.0）。

    本机 wpctl 版本语法是 `set-volume <数字ID> <音量>`
    （`sink:` 前缀会报 not a valid number）。
    """
    try:
        r = subprocess.run(["wpctl", "set-volume", str(serial),
                            f"{vol:.2f}"],
                           capture_output=True, text=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def ensure_audible(playback_device, target_name=None):
    """确保 pw-play 实际会打到的 sink 音量 > 0。

    蓝牙音箱常把自己面板上的音量同步过来（可能为 0）——此时
    sink 在、A2DP 通道通、pw-play 不报错，但全程无声。这是
    "连上却听不见"的主因（区别于 Built-in 空接口：那个连 sink
    都没有物理输出）。为 0 时自动抬到 45%。
    返回提示语（无问题返回 None）。
    """
    try:
        eff = _effective_sink(playback_device, target_name)
    except Exception:
        return None
    if not eff:
        return None
    serial, name, vol = eff
    if vol is not None and vol <= 0.01:
        if set_pw_volume(serial, 0.45):
            print(f"[audio] {name} 音量为 0，已自动调到 45%")
            return (f"{name} 音量原本是 0（这就是听不见的原因），"
                    "已自动调到 45%")
        return f"{name} 音量为 0，自动调音量失败，请手动把该设备音量调大"
    return None


def _bt_a2dp_sink_names() -> set:
    """当前在线的蓝牙 A2DP sink 显示名集合。

    bluez A2DP sink 的 node.name 形如 `bluez_output.<MAC下划线>`，
    以此识别"这是蓝牙音箱/耳机"（区别于 USB 声卡 / 内置）。
    用于自动模式：系统默认掉回 Built-in（无物理输出）时，
    若你主动连了蓝牙，声音就该走蓝牙，而不是转去 USB。
    """
    names = set()
    for serial, sname, _, _ in _list_pw_sinks():
        try:
            info = subprocess.run(["wpctl", "inspect", str(serial)],
                                  capture_output=True, text=True,
                                  timeout=10).stdout
        except Exception:
            continue
        m = re.search(r'node\.name\s*=\s*"([^"]+)"', info)
        if m and "bluez_output." in m.group(1):
            names.add(sname)
    return names


def _target_sink(playback_device: str, target_name=None):
    """决定 pw-play --target 的取值；None = 跟随 PipeWire 默认输出。

    返回值直接是 pw-play 能认的名字/serial（--target 两者皆可）。
    target_name（界面选定的 sink 显示名）→ 在线就直接定向它；
    离线（如蓝牙断开）→ 落到下方 auto 逻辑，不发 Built-in 空接口。
    target_name=None → 智能跟随：
      本机 Jetson AGX Orin 无内置喇叭：默认输出掉回 Built-in 基本
      等于"没有真实输出"（蓝牙断开/USB 被切走后系统常这样回落）。
      此时按优先级定向，否则声音发给空接口，"能播"但听不见：
        1) 已连接的蓝牙 A2DP sink（你主动连了耳机/音箱就给它——
           优先级最高，因为"刚连上的蓝牙"几乎总是用户想要的）
        2) playback_device（设备名子串）对应的 sink（如 USB 声卡）
      默认输出是真实设备（蓝牙/USB/HDMI，用户主动选的）→ 跟随默认，
      蓝牙 A2DP 流程不受影响。显式 plughw:/hw: 前缀 → 跟随默认
      （aplay 回退已指定卡）。
    """
    sinks = _list_pw_sinks()
    if not sinks:
        return None
    if target_name:
        names = {name for _, name, _, _ in sinks}
        if target_name in names:
            return target_name
        # 选定设备离线 → 落到下方 auto 逻辑
    if playback_device.startswith(("plughw:", "hw:", "plug:")):
        return None
    default = next((s for s in sinks if s[2]), None)
    if not default or not default[1].lower().startswith("built-in"):
        return None
    # 默认掉回 Built-in（无物理输出）→ 定向到真实设备
    bt_names = _bt_a2dp_sink_names()
    for _, name, _, _ in sinks:          # 1) 已连蓝牙优先
        if name in bt_names:
            return name
    for _, name, _, _ in sinks:          # 2) 再按配置的播放设备名
        if playback_device.lower() in name.lower():
            return name
    return None


class AudioIO:
    def __init__(self, capture_device="plughw:2,0",
                 playback_device="plughw:2,0",
                 sample_rate=16000,
                 playback_target=None):
        # 设备按名字解析成当前卡号：USB 声卡的 ALSA 卡号每次重启
        # 都会漂移（曾 card 2 → 重启后 card 0，录音随即失效）。
        # 配置里给 plughw:/hw:/plug: 前缀时仍按原样用（显式指定）。
        self.capture_device = _resolve_device(capture_device, "capture")
        self.playback_device = _resolve_device(playback_device, "playback")
        # **原始设备名**（如 "USB Audio"）：智能定向（_target_sink）靠
        # 名字子串匹配 PipeWire sink 显示名，必须用原始名；解析后的
        # plughw:C,D 会让 _target_sink 误判为"显式指定卡"而直接跟随
        # 默认（10/27 根因：自动重定向因此从未生效，默认掉回 Built-in
        # 时纯无声）。plughw 只留给 aplay 回退用。
        self.playback_name = playback_device
        self.sample_rate = sample_rate
        # pw-play 目标 sink 的**显示名**（None="auto" 智能跟随；
        # 名字比 serial 稳：serial 每次重启漂移）。界面播放设备
        # 选择框改这里，立即对后续播放生效。
        self.playback_target = playback_target
        # 播放进程改为**每次播放独立**（存进 _Playback 句柄，不再是
        # 实例共享属性）：旧实现里 play_async 开多个线程共享
        # self._play_proc/self._play_tmp，后一次播放的 stop() 会误杀
        # 前一次的 pw-play、被杀的线程还会落回 aplay 乱播
        # （症状：听完一段就听不了另一段）。
        self._last_playback = None

    # ---------- 录制 ----------
    def record(self, seconds: float, out_path: str) -> bool:
        """录制指定时长的 16kHz mono WAV。成功返回 True。"""
        cmd = ["arecord", "-q", "-f", "S16_LE", "-r", str(self.sample_rate),
               "-c", "1", "-d", str(int(seconds)),
               "-D", self.capture_device, out_path]
        try:
            subprocess.run(cmd, timeout=seconds + 15, capture_output=True)
            ok = os.path.exists(out_path) and os.path.getsize(out_path) > 1000
            if ok:
                print(f"[audio] 已录制 {out_path} ({seconds}s)")
            return ok
        except Exception as e:
            print(f"[audio] 录制失败: {e}")
            return False

    # ---------- 播放 ----------
    def _to_wav_bytes(self, data: bytes) -> bytes:
        """任意音频（mp3/wav/ogg）→ WAV 字节串"""
        if data[:4] == b"RIFF":  # 已是 WAV
            return data
        if MINIAUDIO_AVAILABLE:
            try:
                d = miniaudio.decode(data)
                return _pcm_to_wav(bytes(d.samples), d.sample_rate, d.nchannels)
            except Exception as e:
                print(f"[audio] miniaudio 解码失败: {e}")
        return data

    def play_wav(self, wav_bytes: bytes) -> bool:
        """播放 WAV 字节串（**阻塞**直到播完；可被 stop() 打断）

        优先 pw-play（PipeWire 默认输出，跟随当前选择的设备）；
        失败回退 aplay 直连 playback_device。
        界面按钮请用 play_async()，避免 UI 卡到播完。
        """
        self.stop()
        pb = _Playback(wav_bytes, self.playback_device,
                       self.playback_target, self.playback_name)
        self._last_playback = pb
        return pb.wait()

    def play_async(self, wav_bytes: bytes) -> bool:
        """后台播放（立即返回，音频在后台播完；可被 stop() 打断）。

        任何音频格式（mp3/wav 自动解码）。
        每次播放独立（不干扰彼此）：想同时放两段可以连点，
        想打断当前播放调 stop()。
        """
        pb = _Playback(wav_bytes, self.playback_device,
                       self.playback_target, self.playback_name)
        self._last_playback = pb
        t = threading.Thread(target=pb.run, daemon=True)
        t.start()
        return True

    def probe(self, timeout: float = 6.0) -> bool:
        """探测播放通道是否活着：生成 0.3s 正弦波试播，限时等待。

        返回 True = 通道正常；False = 疑似 A2DP 假连接（通道挂死）。
        探测音人耳几乎不可闻（300Hz 短音、低音量），仅作自检。
        """
        import math
        sr = 16000
        n = int(sr * 0.3)
        pcm = bytearray()
        for i in range(n):
            v = int(8000 * math.sin(2 * math.pi * 300 * i / sr))
            pcm += v.to_bytes(2, "little", signed=True)
        wav = _pcm_to_wav(bytes(pcm), sr, 1)
        tmp = None
        proc = None
        try:
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp.write(wav)
            tmp.close()
            # 必须和实际播放同一个目标（_target_sink），否则默认掉回
            # Built-in 时探测的是空接口、真正的目标设备挂死测不出来
            cmd = ["pw-play"]
            target = _target_sink(self.playback_name,
                                  self.playback_target)
            if target is not None:
                cmd += ["--target", str(target)]
            cmd.append(tmp.name)
            proc = subprocess.Popen(cmd)
            proc.wait(timeout=timeout)
            return proc.returncode == 0
        except subprocess.TimeoutExpired:
            return False
        except Exception:
            return False
        finally:
            if proc and proc.poll() is None:
                proc.kill()
                try:
                    proc.wait(timeout=2)
                except Exception:
                    pass
            if tmp and os.path.exists(tmp.name):
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass

    def play_mp3(self, mp3_bytes: bytes) -> bool:
        """播放 MP3 字节串（先解码为 WAV 再播）"""
        return self.play_wav(self._to_wav_bytes(mp3_bytes))

    def play_file(self, path: str) -> bool:
        """按扩展名播放本地文件"""
        ext = os.path.splitext(path)[1].lower()
        with open(path, "rb") as f:
            data = f.read()
        if ext in (".mp3", ".m4a", ".ogg", ".flac"):
            return self.play_mp3(data)
        return self.play_wav(data)

    def stop(self):
        """打断最近一次播放"""
        pb = self._last_playback
        if pb:
            pb.cancel()

    def selftest(self, path: str = "audio_out/selftest.wav") -> bool:
        """录制 2 秒并回放，验证麦克风+扬声器链路"""
        print("[audio] 自检：请对麦克风说话（2 秒）...")
        if not self.record(2.0, path):
            print("[audio] 自检失败：无法录制")
            return False
        ok = self.play_file(path)
        print("[audio] 自检回放完成" if ok else "[audio] 自检回放失败")
        return ok


class _Playback:
    """一次独立播放（线程安全）：pw-play 优先，失败回退 aplay。

    每个实例持有自己的子进程和临时文件，互不干扰；
    cancel() 只影响自己。
    """

    def __init__(self, wav_bytes: bytes, playback_device: str,
                 playback_target=None, playback_name=None):
        self.wav_bytes = wav_bytes
        self.playback_device = playback_device      # plughw（aplay 回退用）
        self.playback_target = playback_target
        # 原始设备名：pw-play 智能定向用（_target_sink 靠名字匹配 sink）
        self.playback_name = playback_name or playback_device
        self._proc = None

    def _pw_cmd(self, path: str) -> list:
        cmd = ["pw-play"]
        # 定向：界面选定的 sink 优先；未选（auto）时默认掉回
        # Built-in（无物理输出）→ 已连蓝牙优先，其次配置设备
        target = _target_sink(self.playback_name, self.playback_target)
        if target is not None:
            cmd += ["--target", str(target)]
        cmd.append(path)
        return cmd

    def run(self) -> bool:
        """实际播放（阻塞直到播完/被打断）。"""
        wav = self._wav()
        # 1) pw-play（临时文件，本实例独占）
        tmp = None
        try:
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp.write(wav)
            tmp.close()
            self._proc = subprocess.Popen(self._pw_cmd(tmp.name))
            self._proc.wait()
            if self._proc.returncode == 0:
                return True
            print(f"[audio] pw-play 返回 {self._proc.returncode}，尝试 aplay")
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"[audio] pw-play 失败: {e}")
        finally:
            if tmp and os.path.exists(tmp.name):
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass
            self._proc = None
        # 2) aplay 直连回退
        try:
            p = subprocess.Popen(
                ["aplay", "-q", "-D", self.playback_device, "-"],
                stdin=subprocess.PIPE,
            )
            self._proc = p
            p.stdin.write(wav)
            p.stdin.close()
            p.wait()
            return p.returncode == 0
        except Exception as e:
            print(f"[audio] aplay 失败: {e}")
            return False
        finally:
            self._proc = None

    def wait(self) -> bool:
        """阻塞播放（play_wav 用）。"""
        return self.run()

    def cancel(self):
        """打断本次播放（stop() 用）。"""
        p = self._proc
        if p and p.poll() is None:
            p.kill()
            try:
                p.wait(timeout=2)
            except Exception:
                pass

    def _wav(self) -> bytes:
        if self.wav_bytes[:4] == b"RIFF":
            return self.wav_bytes
        if MINIAUDIO_AVAILABLE:
            try:
                d = miniaudio.decode(self.wav_bytes)
                return _pcm_to_wav(bytes(d.samples), d.sample_rate,
                                   d.nchannels)
            except Exception as e:
                print(f"[audio] miniaudio 解码失败: {e}")
        return self.wav_bytes


# ---------- 蓝牙播放通道检查 ----------
# 实测记录（Jetson + Relink 音箱 F8:D3:F0:A9:08:68）：
# 1) A2DP 音频 profile 会偶发断开而 L2CAP 连接仍在（bluez 日志
#    a2dp-sink: connected -> disconnected）→ PipeWire 蓝牙 sink 消失 →
#    默认输出掉回无喇叭的空接口，pw-play 不报错但全程无声。
# 2) A2DP sink 被 WirePlumber 空闲挂起后，重协商可能卡死
#    （"假连接"：pw-play 永久阻塞）。
# 3) 持续静音流"保活"不可行：该音箱约 1.5 分钟后主动断开 A2DP。
# 因此不做常驻保活，改为**按需检查**：sink 存在 + 是默认 + 通道探测
# 三项都过才播；任一失败 → 跑 bt_reset.sh（断开→重连→设默认）→ 复检。

BT_MAC = os.environ.get("BT_DEVICE_MAC", "F8:D3:F0:A9:08:68")
_BT_RESET_SH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "bt_reset.sh")


def bt_status(mac: str = BT_MAC) -> dict:
    """蓝牙播放状态快照。

    返回 {connected, bt_name, sink_id, sink_name, is_default}：
      connected  设备 L2CAP 是否已连接
      sink_id    PipeWire 里该设备 A2DP sink 的 id（不在 = None）
      is_default 该 sink 是否为当前默认输出
    """
    import re
    out = {"connected": False, "bt_name": None, "sink_id": None,
           "sink_name": None, "is_default": False}
    try:
        info = subprocess.run(["bluetoothctl", "--timeout", "5",
                               "info", mac],
                              capture_output=True, text=True,
                              timeout=10).stdout
        out["connected"] = "Connected: yes" in info
        for line in info.splitlines():
            if "Name:" in line:
                out["bt_name"] = line.split(":", 1)[1].strip()
                break
    except Exception:
        return out
    if not out["bt_name"]:
        return out
    try:
        status = subprocess.run(["wpctl", "status"], capture_output=True,
                                text=True, timeout=10).stdout
    except Exception:
        return out
    # 只解析 Sinks: 区块（Sources 区块也有 [vol:，且行首带 │ 边框字符，
    # 用 search 而非 match）
    start = status.find("Sinks:")
    end = status.find("Sink endpoints", start) if start >= 0 else -1
    block = status[start:end] if start >= 0 and end > start else ""
    default_id = None
    for line in block.splitlines():
        m = re.search(r"(\*?)\s*(\d+)\.\s+(.+?)\s+\[vol:", line)
        if m and m.group(1) == "*":
            default_id = int(m.group(2))
    # sink 按 node.name 里的 MAC 精确定位（显示名不含 MAC：实测该设备
    # 显示名是 "BS-32D" 而非蓝牙名，按 bt_name 子串匹配会漏）
    bt_nodes = _pw_node_names(mac)
    for serial, sname, _, _ in _list_pw_sinks():
        info = None
        try:
            info = subprocess.run(["wpctl", "inspect", str(serial)],
                                  capture_output=True, text=True,
                                  timeout=10).stdout
        except Exception:
            pass
        if info and re.search(r'node\.name\s*=\s*"([^"]+)"', info):
            node = re.search(r'node\.name\s*=\s*"([^"]+)"', info).group(1)
            if node in bt_nodes:
                out["sink_id"], out["sink_name"] = serial, sname
                break
    out["is_default"] = (out["sink_id"] is not None
                         and default_id == out["sink_id"])
    return out
