"""
services/llm_client.py
文言文翻译与回答服务

generate_turn(text, history) -> {"translation": ..., "reply": ...}

优先级：
1. 本地 llama-server（默认 http://127.0.0.1:8080，Qwen3-30B-A3B，无需密钥）
2. 配置 LLM_API_KEY 时回退到云端 OpenAI 兼容接口
3. 都不可用时本地规则回退（词典翻译 + 固定文言应答）
"""
import json
import os
import re

import httpx

from classical_translator import simple_translate
from language.style_prompt import SYSTEM_PROMPT, MAX_REPLY_CHARS

try:
    from opencc import OpenCC
    _T2S = OpenCC("t2s")

    def _to_simplified(text: str) -> str:
        # 模型偶发输出繁体，古音库是简体字表 → 统一转简体
        try:
            return _T2S.convert(text)
        except Exception:
            return text
except ImportError:
    def _to_simplified(text: str) -> str:
        return text

# 本地优先：llama-server (llama.cpp) OpenAI 兼容接口
LOCAL_BASE = os.environ.get("LOCAL_LLM_BASE", "http://127.0.0.1:8080/v1")
LOCAL_MODEL = os.environ.get("LOCAL_LLM_MODEL", "")  # 空 = 用服务端的默认模型

# 云端可选
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


def _local_fallback(text: str):
    """规则回退：词典翻译 + 意图匹配应答"""
    translation = simple_translate(text)
    reply = _DEFAULT_REPLY
    for keys, canned in _LOCAL_REPLIES:
        if any(k in text for k in keys):
            reply = canned
            break
    return {"translation": translation, "reply": reply}


def _extract_json(raw: str, original_text: str) -> dict:
    """从模型输出中稳健地提取 {translation, reply}"""
    raw = raw.strip()
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
    return {"translation": simple_translate(original_text), "reply": raw}


def _build_messages(text: str, history):
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in (history or [])[-6:]:
        if turn.get("user"):
            msgs.append({"role": "user", "content": turn["user"]})
        if turn.get("assistant"):
            msgs.append({"role": "assistant", "content": turn["assistant"]})
    msgs.append({"role": "user", "content": text})
    return msgs


def _call_chat(base: str, model: str, text: str, history, key=""):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    payload = {"messages": _build_messages(text, history),
               "temperature": 0.7, "max_tokens": 300}
    if model:
        payload["model"] = model
    # 本机服务不走代理（环境里的 ALL_PROXY 指向不稳定的本地代理）
    trust_env = "127.0.0.1" not in base and "localhost" not in base
    r = httpx.post(f"{base}/chat/completions", headers=headers,
                   json=payload, timeout=120.0, trust_env=trust_env)
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"]
    return _extract_json(content, text)


def generate_turn(text: str, history=None) -> dict:
    """单轮对话统一入口：本地 Qwen3 → 云端 → 规则回退"""
    out = None
    # 1) 本地 llama-server
    try:
        out = _call_chat(LOCAL_BASE, LOCAL_MODEL, text, history)
        out["source"] = "local-qwen"
    except Exception as e:
        print(f"[llm] 本地 LLM 不可用: {e.__class__.__name__}")
    # 2) 云端（需 key）
    if out is None and API_KEY:
        try:
            out = _call_chat(LLM_BASE, LLM_MODEL, text, history, key=API_KEY)
            out["source"] = "cloud"
        except Exception as e:
            print(f"[llm] 云端调用失败: {e.__class__.__name__}")
    # 3) 规则回退
    if out is None:
        out = _local_fallback(text)
        out["source"] = "local-rules"
    # 繁体 → 简体（古音库字表为简体）
    out["translation"] = _to_simplified(out.get("translation", ""))
    out["reply"] = _to_simplified(out["reply"])
    # 限制长度，防止生僻字/长句拉低古音覆盖率
    if len(out["reply"]) > MAX_REPLY_CHARS:
        out["reply"] = out["reply"][:MAX_REPLY_CHARS]
    return out
