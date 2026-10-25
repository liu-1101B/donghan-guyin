"""
services/llm_client.py
文言文翻译与回答服务

generate_turn(text, history) -> {"translation": ..., "reply": ...}

- 配置 LLM_API_KEY（OpenAI 兼容 /chat/completions）时走云端高质量生成；
- 未配置时用本地回退：词典式翻译 + 规则式文言应答（保证离线可运行）。
"""
import json
import os
import re

import httpx

from classical_translator import simple_translate
from language.style_prompt import SYSTEM_PROMPT, TRANSLATE_ONLY_PROMPT, MAX_REPLY_CHARS

LLM_BASE = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")
API_KEY = os.environ.get("LLM_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")

# 本地回退用的固定应答语料（常见意图 → 文言应答）
_LOCAL_REPLIES = [
    (("你好", "您好", "嗨", "哈喽", "在吗", "你是谁"), "君远来何所？吾乃洛阳一腐儒，愿与君闲话片刻。"),
    (("名字", "贵姓", "你叫", "什么名"), "吾无名氏，君若赐号，吾当铭之。"),
    (("天气", "冷", "热", "下雨", "风", "雪", "晴"), "洛阳近日天朗气清，惠风和畅，宜于园中徐行。"),
    (("饿", "饭", "吃", "食", "茶"), "饥则食，渴则饮，此天理也。吾备有浊酒粗茶，愿与君共之。"),
    (("累", "倦", "困", "睡", "困了"), "劳神者当养其息。且就榻上小憩，吾为君守此清夜。"),
    (("开心", "高兴", "快乐", "太好了"), "君心欣然，吾亦与有荣焉。人生快意，莫过于斯。"),
    (("难过", "伤心", "悲伤", "烦", "无聊"), "人生天地间，忽如远行客。愿君暂遣烦忧，与吾共话古今。"),
    (("故事", "讲个", "说个", "典故"), "昔者庄周梦蝶，不知庄周之化为蝶与，蝶之化为庄周与？奇哉。"),
    (("诗", "作诗", "吟", "赋"), "试为君吟曰：洛阳何浩浩，河水扬清波。愿言常相思，岁月如逝何。"),
    (("谢谢", "多谢", "感谢", "辛苦"), "不足挂齿。与君一席，吾之幸也。"),
    (("再见", "拜拜", "走了", "告辞"), "日薄西山，后会可期。君其珍重，吾当长念。"),
    (("喜欢", "爱"), "情之所钟，正在我辈。愿与君长相守，共此良辰。"),
]
_DEFAULT_REPLY = "善哉。君之言，吾闻之矣。愿闻其详。"


def _local_turn(text: str):
    """本地规则回退：词典翻译 + 意图匹配应答"""
    translation = simple_translate(text)
    reply = _DEFAULT_REPLY
    low = text
    for keys, canned in _LOCAL_REPLIES:
        if any(k in low for k in keys):
            reply = canned
            break
    return {"translation": translation, "reply": reply}


def _extract_json(raw: str, original_text: str) -> dict:
    """从模型输出中稳健地提取 {translation, reply}"""
    raw = raw.strip()
    # 去掉可能的 markdown 代码块
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
    if m:
        raw = m.group(1)
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and "reply" in obj:
            return {
                "translation": str(obj.get("translation", "")),
                "reply": str(obj["reply"]),
            }
    except Exception:
        pass
    # 兜底：整个输出当作 reply，翻译用本地词典
    return {"translation": simple_translate(original_text), "reply": raw}


def _cloud_turn(text: str, history):
    key = API_KEY
    if not key:
        return None
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in history[-6:]:
        if turn.get("user"):
            msgs.append({"role": "user", "content": turn["user"]})
        if turn.get("assistant"):
            msgs.append({"role": "assistant", "content": turn["assistant"]})
    msgs.append({"role": "user", "content": text})
    try:
        r = httpx.post(
            f"{LLM_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": LLM_MODEL, "messages": msgs, "temperature": 0.7,
                  "max_tokens": 300},
            timeout=20.0,
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        return _extract_json(content, text)
    except Exception as e:
        print(f"[llm] 云端调用失败，回退本地: {e}")
        return None


def generate_turn(text: str, history=None) -> dict:
    """单轮对话统一入口：返回 {translation, reply, source}"""
    history = history or []
    out = _cloud_turn(text, history)
    if out:
        # 限制长度，防止生僻字/长句拉低古音覆盖率
        if len(out["reply"]) > MAX_REPLY_CHARS:
            out["reply"] = out["reply"][:MAX_REPLY_CHARS]
        out["source"] = "cloud"
        return out
    out = _local_turn(text)
    out["source"] = "local"
    return out
