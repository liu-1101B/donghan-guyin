"""
robot/voice_router.py
语音模式路由：自然语音 / 东汉古音，运行时可切换（无需重启）。
"""
from language.turn_engine import (
    MODE_NATURAL, MODE_ANCIENT, make_turn,
)


class VoiceRouter:
    MODES = (MODE_NATURAL, MODE_ANCIENT)

    def __init__(self, default_mode: str = MODE_NATURAL, pitch: int = 130):
        self.mode = default_mode if default_mode in self.MODES else MODE_NATURAL
        self.pitch = pitch

    def set_mode(self, mode: str) -> bool:
        if mode not in self.MODES:
            return False
        self.mode = mode
        return True

    def toggle(self) -> str:
        self.mode = MODE_ANCIENT if self.mode == MODE_NATURAL else MODE_NATURAL
        return self.mode

    def route(self, user_text: str, history=None):
        """按当前模式生成音频，返回 Turn"""
        return make_turn(user_text, mode=self.mode,
                         history=history, pitch=self.pitch)

    def label(self) -> str:
        return "自然语音" if self.mode == MODE_NATURAL else "东汉古音"
