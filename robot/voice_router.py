"""
robot/voice_router.py
语音模式路由：自然语音 / 东汉古韵，运行时可切换（无需重启）。
同时持有音色/语速等可调参数，界面上改完直接生效。
"""
from language.turn_engine import (
    MODE_NATURAL, MODE_ANCIENT, make_turn,
)


class VoiceRouter:
    MODES = (MODE_NATURAL, MODE_ANCIENT)

    def __init__(self, default_mode: str = MODE_NATURAL, pitch: int = 130,
                 voice: str = None, rate: str = None, speed: float = 1.0):
        self.mode = default_mode if default_mode in self.MODES else MODE_NATURAL
        self.pitch = pitch            # 古韵基频 Hz（音色高低）
        self.voice = voice            # 自然语音 Edge TTS 音色 id（None=默认）
        self.rate = rate              # 自然语音语速（None=默认 -10%）
        self.speed = speed            # 古韵语速倍率（1.0=正常）

    def set_mode(self, mode: str) -> bool:
        if mode not in self.MODES:
            return False
        self.mode = mode
        return True

    def toggle(self) -> str:
        self.mode = MODE_ANCIENT if self.mode == MODE_NATURAL else MODE_NATURAL
        return self.mode

    def route(self, user_text: str, history=None):
        """按当前模式生成音频，返回 Turn（应用当前音色/语速设置）"""
        return make_turn(user_text, mode=self.mode,
                         history=history, pitch=self.pitch,
                         voice=self.voice, rate=self.rate,
                         speed=self.speed)

    def label(self) -> str:
        return "自然语音" if self.mode == MODE_NATURAL else "东汉古韵"
