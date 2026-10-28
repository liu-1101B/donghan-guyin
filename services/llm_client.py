"""
services/llm_client.py
文言文翻译与回答服务

generate_turn(text, history) -> {"translation": ..., "reply": ...}

优先级：
1. 本地 llama-server（默认 http://127.0.0.1:8080，Qwen3-30B-A3B，无需密钥）
2. 配置 LLM_API_KEY 时回退到云端 OpenAI 兼容接口
3. 都不可用时本地规则回退（词典翻译 + 固定文言应答）
"""
import ipaddress
import json
import os
import re
from urllib.parse import urlparse

import httpx

from classical_translator import simple_translate
from language.style_prompt import SYSTEM_PROMPT, MAX_REPLY_CHARS

try:
    from opencc import OpenCC
    _T2S = OpenCC("t2s")

    def _to_simplified(text: str) -> str:
        # 模型偶发输出繁体，古韵库是简体字表 → 统一转简体
        try:
            return _T2S.convert(text)
        except Exception:
            return text
except ImportError:
    def _to_simplified(text: str) -> str:
        return text

# 模型选择：
# auto  = 优先 OpenAI 兼容模型服务，失败后尝试云端，最后规则回退
# local = 只调用 LOCAL_LLM_BASE（可为本机，也可为局域网/自建服务器）
# cloud = 只调用 LLM_BASE_URL，不尝试本机模型
# rules = 不访问任何模型服务，只用内置词典/规则
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "auto").strip().lower()

# OpenAI 兼容模型服务。默认是本机 llama-server，也可指向局域网远程服务器。
LOCAL_BASE = os.environ.get("LOCAL_LLM_BASE", "http://127.0.0.1:8080/v1").rstrip("/")
LOCAL_MODEL = os.environ.get("LOCAL_LLM_MODEL", "")  # 空 = 使用服务端默认模型
LOCAL_API_KEY = os.environ.get("LOCAL_LLM_API_KEY", "")

# 云端 OpenAI 兼容接口
LLM_BASE = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")
API_KEY = os.environ.get("LLM_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")

_VALID_PROVIDERS = {"auto", "local", "cloud", "rules"}

# 本地回退用的固定应答语料（常见意图 → (文言应答, 白话应答)）
_LOCAL_REPLIES = [
    (("你好", "您好", "嗨", "哈喽", "在吗", "你是谁"),
     "君远来何所？吾乃洛阳一腐儒，愿与君闲话片刻。",
     "你从大老远来做什么？我是个洛阳的书呆子，想跟你聊一会儿。"),
    (("名字", "贵姓", "你叫", "什么名"),
     "吾无名氏，君若赐号，吾当铭之。",
     "我没什么名字，你要是给我起个号，我会记在心里。"),
    (("天气", "冷", "热", "下雨", "风", "雪", "晴"),
     "洛阳近日天朗气清，惠风和畅，宜于园中徐行。",
     "洛阳这几天天气很好，风也柔和，适合到园子里慢慢走走。"),
    (("饿", "饭", "吃", "食", "茶"),
     "饥则食，渴则饮，此天理也。吾备有浊酒粗茶，愿与君共之。",
     "饿了就吃，渴了就喝，这是天经地义。我备了点酒和粗茶，咱们一起喝。"),
    (("累", "倦", "困", "睡", "困了"),
     "劳神者当养其息。且就榻上小憩，吾为君守此清夜。",
     "用脑多了要休息。你就到榻上睡一会儿，我替你守着这清静的夜。"),
    (("开心", "高兴", "快乐", "太好了"),
     "君心欣然，吾亦与有荣焉。人生快意，莫过于斯。",
     "你高兴我也跟着高兴。人生快事，莫过于此了。"),
    (("难过", "伤心", "悲伤", "烦", "无聊"),
     "人生天地间，忽如远行客。愿君暂遣烦忧，与吾共话古今。",
     "人在天地间，就像匆匆过客。希望你暂时放下烦恼，跟我聊聊古今。"),
    (("故事", "讲个", "说个", "典故"),
     "昔者庄周梦蝶，不知庄周之化为蝶与，蝶之化为庄周与？奇哉。",
     "从前庄周梦见自己变成蝴蝶，分不清是庄周梦成蝴蝶，还是蝴蝶梦成庄周。真奇妙。"),
    (("诗", "作诗", "吟", "赋"),
     "试为君吟曰：洛阳何浩浩，河水扬清波。愿言常相思，岁月如逝何。",
     "给你念一首：洛阳多么浩荡，河水扬起清波。愿我们常常思念，岁月怎能如流沙。"),
    (("谢谢", "多谢", "感谢", "辛苦"),
     "不足挂齿。与君一席，吾之幸也。",
     "不客气。能跟你坐一坐，是我的运气。"),
    (("再见", "拜拜", "走了", "告辞"),
     "日薄西山，后会可期。君其珍重，吾当长念。",
     "太阳要下山了，我们还会再见的。你多保重，我会一直记得你。"),
    (("喜欢", "爱"),
     "情之所钟，正在我辈。愿与君长相守，共此良辰。",
     "感情所倾注的，正是我们这类人。愿和你长相守，共度这美好时光。"),
]
_DEFAULT_REPLY = "善哉。君之言，吾闻之矣。愿闻其详。"
_DEFAULT_REPLY_MODERN = "说得好。你的话我听到了，想听听更多。"


def _local_fallback(text: str):
    """规则回退：词典翻译 + 意图匹配应答（含白话版）"""
    translation = simple_translate(text)
    reply, reply_modern = _DEFAULT_REPLY, _DEFAULT_REPLY_MODERN
    for keys, canned, modern in _LOCAL_REPLIES:
        if any(k in text for k in keys):
            reply, reply_modern = canned, modern
            break
    return {"translation": translation, "reply": reply,
            "reply_modern": reply_modern}


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
                "reply_modern": str(obj.get("reply_modern", "")),
            }
    except Exception:
        pass
    return {"translation": simple_translate(original_text), "reply": raw,
            "reply_modern": ""}


def _build_messages(text: str, history):
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in (history or [])[-6:]:
        if turn.get("user"):
            msgs.append({"role": "user", "content": turn["user"]})
        if turn.get("assistant"):
            msgs.append({"role": "assistant", "content": turn["assistant"]})
    msgs.append({"role": "user", "content": text})
    return msgs


def _trust_env_for_endpoint(base: str) -> bool:
    """Do not route loopback/private-LAN model traffic through public proxies."""
    host = (urlparse(base).hostname or "").strip("[]").lower()
    if not host:
        return True
    if host == "localhost" or host.endswith(".localhost"):
        return False
    try:
        address = ipaddress.ip_address(host)
        if address.is_loopback or address.is_private or address.is_link_local:
            return False
    except ValueError:
        # Hostnames such as jetson.local can opt out through standard NO_PROXY.
        pass
    return True


def _call_chat(base: str, model: str, text: str, history, key="", timeout=120.0):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    payload = {"messages": _build_messages(text, history),
               "temperature": 0.7, "max_tokens": 300}
    if model:
        payload["model"] = model
    # Local/LAN inference should not accidentally go via the user's public proxy.
    trust_env = _trust_env_for_endpoint(base)
    # 限制连接阶段等待时间；模型生成本身仍可使用较长读取超时。
    timeout_cfg = httpx.Timeout(timeout, connect=min(5.0, timeout))
    r = httpx.post(f"{base}/chat/completions", headers=headers,
                   json=payload, timeout=timeout_cfg, trust_env=trust_env)
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"]
    return _extract_json(content, text)


def _selected_provider() -> str:
    """Return a safe provider mode; invalid values fall back to auto."""
    provider = LLM_PROVIDER
    if provider not in _VALID_PROVIDERS:
        print(f"[llm] 未知 LLM_PROVIDER={provider!r}，改用 auto")
        return "auto"
    return provider


def generate_turn(text: str, history=None) -> dict:
    """统一入口：按 LLM_PROVIDER 调用模型，失败时退回内置规则。

    auto: local-compatible endpoint -> cloud (if configured) -> rules
    local: LOCAL_LLM_BASE only (it may point to a LAN model server)
    cloud: LLM_BASE_URL only
    rules: skip all network model calls
    """
    provider = _selected_provider()
    out = None

    if provider in {"auto", "local"}:
        try:
            out = _call_chat(
                LOCAL_BASE, LOCAL_MODEL, text, history,
                key=LOCAL_API_KEY, timeout=120.0,
            )
            out["source"] = "local-model"
        except Exception as e:
            print(f"[llm] 模型服务 {LOCAL_BASE} 不可用: {e.__class__.__name__}")

    if out is None and provider in {"auto", "cloud"}:
        if API_KEY:
            try:
                out = _call_chat(
                    LLM_BASE, LLM_MODEL, text, history,
                    key=API_KEY, timeout=60.0,
                )
                out["source"] = "cloud"
            except Exception as e:
                print(f"[llm] 云端模型调用失败: {e.__class__.__name__}")
        else:
            print("[llm] 未配置云端 API 密钥；如需云端模型，请设置 LLM_API_KEY")

    # rules mode is explicitly offline; auto/local/cloud all degrade here on failure.
    if out is None:
        out = _local_fallback(text)
        out["source"] = "local-rules"
    # 繁体 → 简体（古韵库字表为简体）
    out["translation"] = _to_simplified(out.get("translation", ""))
    out["reply"] = _to_simplified(out["reply"])
    out["reply_modern"] = _to_simplified(out.get("reply_modern", ""))
    # 限制长度，防止生僻字/长句拉低古韵覆盖率
    if len(out["reply"]) > MAX_REPLY_CHARS:
        out["reply"] = out["reply"][:MAX_REPLY_CHARS]
    return out
