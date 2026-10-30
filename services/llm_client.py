"""
services/llm_client.py
文言文翻译与回答服务。

仅有两条路径：
- 配置 LLM_API_KEY / OPENAI_API_KEY：调用 LLM_BASE_URL 指定的大模型 API；
- 未配置密钥：不访问任何模型服务，只使用本地词典和预设应答。
本地词典未命中时 reply 为空，交由调用方只播放用户输入的古汉语翻译。

词典模式另有一个显式开关 allow_llm_translate（默认关）：词典未命中且
配置了密钥时，只用大模型补「翻译」一层（结果标注 translation_source="llm"）；
reply 仍然为空——「宁可不答不编造」的契约不因 LLM 参与而放宽。
"""
import ipaddress
import json
import os
import re
from urllib.parse import urlparse

import httpx

from classical_translator import (
    simple_translate,
    TRANSLATION_DICT,
    build_translate_prompt,
)
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

def _safe_log(message: str) -> None:
    """Logging must never break dictionary fallback on legacy Windows consoles."""
    try:
        print(message)
    except UnicodeEncodeError:
        try:
            print(message.encode("ascii", "backslashreplace").decode("ascii"))
        except Exception:
            pass


# 可选的大模型 API：填写密钥时调用所配置的 OpenAI 兼容接口；
# 密钥为空时完全不尝试本地/远程模型，直接使用本地词典应答。
LLM_BASE = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")
API_KEY = os.environ.get("LLM_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")


def refresh_credentials() -> dict:
    """Re-read the three settings from the environment.

    The web UI writes them into .env and updates os.environ, then calls this;
    module-level constants are captured at import time, so without it a key
    typed into the page would only take effect after restarting the process.
    """
    global LLM_BASE, LLM_MODEL, API_KEY
    LLM_BASE = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    API_KEY = os.environ.get("LLM_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")
    return {"base": LLM_BASE, "model": LLM_MODEL, "has_key": bool(API_KEY)}

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


# 字级词典覆盖：所有出现在词典 key 里的 CJK 字。
# 注意这是字级近似——只出现在多字 key 里的字（如「自己」的「子」）也算覆盖，
# 单字未必译得动。该集合只用于 (a) 如实标注翻译覆盖 (b) 触发 LLM 翻译回退，
# 绝不用于悄悄回填翻译结果。
_CJK_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")
_DICT_CHAR_SET = frozenset("".join(TRANSLATION_DICT.keys()))


def dict_miss_chars(text: str) -> list:
    """按出现顺序、去重，返回 text 中不出现在任何词典 key 里的 CJK 字。"""
    missed = []
    for ch in text:
        if (_CJK_CHAR_RE.fullmatch(ch)
                and ch not in _DICT_CHAR_SET
                and ch not in missed):
            missed.append(ch)
    return missed


def _local_fallback(text: str, allow_llm_translate: bool = False):
    """词典模式回退：只使用本地词典/预设应答；没有命中就不编造回答。

    allow_llm_translate=True 且已配置密钥时，词典未命中会请大模型补
    「翻译」一层（translation_source="llm"，词典结果留在 dict_translation）；
    reply 仍为空——不编造回答的契约不放宽。
    """
    translation = simple_translate(text)
    missed = dict_miss_chars(text)
    for keys, canned, modern in _LOCAL_REPLIES:
        if any(k in text for k in keys):
            return {
                "translation": translation,
                "reply": canned,
                "reply_modern": modern,
                "source": "local-dictionary",
                "translation_source": "dictionary",
                "missed_chars": missed,
            }
    if missed and allow_llm_translate and API_KEY:
        try:
            llm_translation = _call_translate(
                LLM_BASE, LLM_MODEL, text, key=API_KEY, timeout=60.0).strip()
        except Exception as e:
            _safe_log(f"[llm] LLM 翻译回退失败，保留词典翻译：{e}")
            llm_translation = ""
        if llm_translation:
            return {
                "translation": llm_translation,
                "reply": "",
                "reply_modern": "",
                "source": "local-dictionary-miss",
                "translation_source": "llm",
                "dict_translation": translation,
                "missed_chars": missed,
            }
    return {
        "translation": translation,
        "reply": "",
        "reply_modern": "",
        "source": "local-dictionary-miss",
        "translation_source": "dictionary",
        "missed_chars": missed,
    }


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
    # 解析失败时不能把残缺 JSON 当回答返回：截断的输出会长这样
    # {"translation": "今日天朗，与友步于河滨。", "reply": "风和日暖，临水
    # 直接当 reply 用的话，界面会显示一段半截 JSON。让调用方走回退。
    if raw.startswith("{"):
        raise ValueError("模型返回的 JSON 不完整（可能被 max_tokens 截断）")
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


def _call_chat(base: str, model: str, text: str, history, key="", timeout=120.0,
               max_tokens=2048):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    payload = {"messages": _build_messages(text, history),
               "temperature": 0.7, "max_tokens": max_tokens}
    if model:
        payload["model"] = model
    # Local/LAN inference should not accidentally go via the user's public proxy.
    trust_env = _trust_env_for_endpoint(base)
    # 限制连接阶段等待时间；模型生成本身仍可使用较长读取超时。
    timeout_cfg = httpx.Timeout(timeout, connect=min(5.0, timeout))
    r = httpx.post(f"{base}/chat/completions", headers=headers,
                   json=payload, timeout=timeout_cfg, trust_env=trust_env)
    r.raise_for_status()
    data = r.json()
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = message.get("content") or ""
    finish = choice.get("finish_reason")

    # 推理模型（如 deepseek-flash）会先写 reasoning_content，正文排在后面。
    # max_tokens 太小的话推理就把额度吃光，正文被截断甚至为空。
    if finish == "length":
        reasoning = len(message.get("reasoning_content") or "")
        raise RuntimeError(
            f"输出被截断：max_tokens={max_tokens}，其中推理内容 {reasoning} 字")
    if not content.strip():
        raise RuntimeError("模型返回空内容")
    return _extract_json(content, text)


def _call_translate(base: str, model: str, text: str, key="", timeout=60.0,
                    max_tokens=2048):
    """只翻译的调用：prompt 要求纯文言输出，返回原始文本（不做 JSON 解析）。

    与 _call_chat 不同，这里绝不把残缺 JSON 当翻译返回：输出为空或被
    截断就抛异常，由调用方回退词典翻译。
    """
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    payload = {"messages": [{"role": "user",
                             "content": build_translate_prompt(text)}],
               "temperature": 0.7, "max_tokens": max_tokens}
    if model:
        payload["model"] = model
    # 与 _call_chat 相同的代理策略：本地/局域网端点不走公网代理。
    trust_env = _trust_env_for_endpoint(base)
    timeout_cfg = httpx.Timeout(timeout, connect=min(5.0, timeout))
    r = httpx.post(f"{base}/chat/completions", headers=headers,
                   json=payload, timeout=timeout_cfg, trust_env=trust_env)
    r.raise_for_status()
    data = r.json()
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = (message.get("content") or "").strip()
    finish = choice.get("finish_reason")
    if finish == "length":
        reasoning = len(message.get("reasoning_content") or "")
        raise RuntimeError(
            f"输出被截断：max_tokens={max_tokens}，其中推理内容 {reasoning} 字")
    if not content:
        raise RuntimeError("模型返回空内容")
    return content


def generate_turn(text: str, history=None, mode: str = None,
                  allow_llm_translate: bool = False) -> dict:
    """两条明确路线：mode='api' 用大模型；mode='dictionary' 只查本地词典。

    mode=None 时供命令行调用：已配置密钥则用 API，否则用词典。
    API 调用失败会回退词典；词典未命中时 reply/reply_modern 均为空，
    上层必须只播放 translation 的古汉语音频，不得补造默认回答。

    allow_llm_translate（仅词典模式生效）：词典未命中时只请 LLM 补
    「翻译」一层并标注 translation_source="llm"；reply 恒为空——
    LLM 翻译成功也不编造回答。
    """
    selected = (mode or ("api" if API_KEY else "dictionary")).strip().lower()
    if selected not in {"api", "dictionary"}:
        selected = "dictionary"

    out = None
    if selected == "api":
        if not API_KEY:
            _safe_log("[llm] 当前选择大模型 API 模式，但未配置 LLM_API_KEY；改用本地词典")
        else:
            # 推理模型可能把首轮 token 全花在 reasoning 上，截断时加预算重试一次
            for budget in (2048, 4096):
                try:
                    out = _call_chat(LLM_BASE, LLM_MODEL, text, history,
                                     key=API_KEY, timeout=60.0, max_tokens=budget)
                    # api 模式的翻译必然来自大模型，标注来源供界面展示
                    out["translation_source"] = "llm"
                    out["source"] = "cloud"
                    break
                except Exception as e:
                    detail = f"{e.__class__.__name__}: {e}"
                    if budget == 2048 and "截断" in str(e):
                        _safe_log(f"[llm] {detail}；用更大 max_tokens 重试")
                        continue
                    _safe_log(f"[llm] 云端 API 调用失败，改用本地词典：{detail}")
                    # 非截断失败（断网、401、超时……）加大 max_tokens 没有意义，
                    # 直接回退词典，不向同一端点重复发起调用。
                    break
        # API 失败/未配置时不再向同一个端点发起第二次 LLM 调用，
        # 直接词典回退（allow_llm_translate 仅词典模式生效）。
        if out is None:
            out = _local_fallback(text)
    else:
        out = _local_fallback(text, allow_llm_translate)
    # 繁体 → 简体（古韵库字表为简体）
    out["translation"] = _to_simplified(out.get("translation", ""))
    out["reply"] = _to_simplified(out["reply"])
    out["reply_modern"] = _to_simplified(out.get("reply_modern", ""))
    # 限制长度，防止生僻字/长句拉低古韵覆盖率
    if len(out["reply"]) > MAX_REPLY_CHARS:
        out["reply"] = out["reply"][:MAX_REPLY_CHARS]
    return out
