"""
robot/session.py
多轮对话状态：保存最近 N 轮（默认 8），供 LLM 保持上下文。
"""
from collections import deque


class Session:
    def __init__(self, max_turns: int = 8):
        self.max_turns = max_turns
        self.turns = deque(maxlen=max_turns)

    def add(self, user_text: str, assistant_text: str):
        self.turns.append({"user": user_text, "assistant": assistant_text})

    def history(self) -> list:
        return list(self.turns)

    def reset(self):
        self.turns.clear()

    def stats(self) -> dict:
        return {"turns": len(self.turns), "capacity": self.max_turns}
