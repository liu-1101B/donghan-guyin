"""Tests for the two supported LLM routes: API and local dictionary."""
import json
import os
import unittest
from unittest.mock import patch

import services.llm_client as llm


MODEL_REPLY = {
    "translation": "今天天气甚佳。",
    "reply": "今日天朗气清。",
    "reply_modern": "今天天气很好。",
}


class _FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": {"content": json.dumps(MODEL_REPLY)}}]}


class LLMModeTests(unittest.TestCase):
    def test_api_mode_calls_configured_model_when_key_is_present(self):
        with (
            patch.object(llm, "API_KEY", "test-secret"),
            patch.object(llm, "LLM_BASE", "https://example.invalid/v1"),
            patch.object(llm, "LLM_MODEL", "test-model"),
            patch.object(llm, "_call_chat", return_value=dict(MODEL_REPLY)) as call,
        ):
            result = llm.generate_turn("今天天气怎么样？", mode="api")

        self.assertEqual(result["source"], "cloud")
        call.assert_called_once()
        self.assertEqual(call.call_args.args[0], "https://example.invalid/v1")
        self.assertEqual(call.call_args.args[1], "test-model")
        self.assertEqual(call.call_args.kwargs["key"], "test-secret")

    def test_dictionary_mode_never_calls_model_api(self):
        with (
            patch.object(llm, "API_KEY", "test-secret"),
            patch.object(llm, "_call_chat") as call,
        ):
            result = llm.generate_turn("你好", mode="dictionary")

        call.assert_not_called()
        self.assertEqual(result["source"], "local-dictionary")
        self.assertTrue(result["reply"])

    def test_dictionary_miss_returns_no_fabricated_reply(self):
        with (
            patch.object(llm, "API_KEY", "test-secret"),
            patch.object(llm, "_call_chat") as call,
        ):
            result = llm.generate_turn("量子计算如何影响星际航行？", mode="dictionary")

        call.assert_not_called()
        self.assertEqual(result["source"], "local-dictionary-miss")
        self.assertTrue(result["translation"])
        self.assertEqual(result["reply"], "")
        self.assertEqual(result["reply_modern"], "")

    def test_api_mode_without_key_uses_dictionary_without_network(self):
        with (
            patch.object(llm, "API_KEY", ""),
            patch.object(llm, "_call_chat") as call,
        ):
            result = llm.generate_turn("你好", mode="api")

        call.assert_not_called()
        self.assertEqual(result["source"], "local-dictionary")
        self.assertTrue(result["reply"])

    def test_api_failure_uses_dictionary_and_does_not_make_up_unknown_reply(self):
        with (
            patch.object(llm, "API_KEY", "test-secret"),
            patch.object(llm, "_call_chat", side_effect=ConnectionError("offline")) as call,
        ):
            result = llm.generate_turn("量子计算如何影响星际航行？", mode="api")

        call.assert_called_once()
        self.assertEqual(result["source"], "local-dictionary-miss")
        self.assertEqual(result["reply"], "")
        self.assertEqual(result["reply_modern"], "")

    def test_private_lan_endpoint_bypasses_public_proxy(self):
        with patch.object(llm.httpx, "post", return_value=_FakeResponse()) as post:
            llm._call_chat(
                "http://192.168.1.20:8080/v1", "test-model", "你好", []
            )
        self.assertFalse(post.call_args.kwargs["trust_env"])

    def test_public_api_endpoint_can_use_proxy_environment(self):
        with patch.object(llm.httpx, "post", return_value=_FakeResponse()) as post:
            llm._call_chat(
                "https://api.example.invalid/v1", "test-model", "你好", []
            )
        self.assertTrue(post.call_args.kwargs["trust_env"])


class LLMCredentialRefreshTests(unittest.TestCase):
    """界面里填完 API 后必须立刻生效，不能等重启进程。"""

    def tearDown(self):
        # 环境变量由 patch.dict 还原，这里把模块常量同步回去
        llm.refresh_credentials()

    def test_refresh_picks_up_environment_values(self):
        with patch.dict(
            os.environ,
            {
                "LLM_BASE_URL": "http://127.0.0.1:9/v1/",
                "LLM_MODEL": "typed-in-ui",
                "LLM_API_KEY": "sk-ui-9999",
            },
            clear=False,
        ):
            info = llm.refresh_credentials()

        self.assertEqual(info["base"], "http://127.0.0.1:9/v1")   # 去尾斜杠
        self.assertEqual(info["model"], "typed-in-ui")
        self.assertTrue(info["has_key"])
        self.assertEqual(llm.API_KEY, "sk-ui-9999")
        self.assertEqual(llm.LLM_MODEL, "typed-in-ui")

    def test_empty_key_marks_api_mode_unavailable(self):
        with patch.dict(os.environ, {"LLM_API_KEY": ""}, clear=False):
            with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
                info = llm.refresh_credentials()
        self.assertFalse(info["has_key"])


class DictMissCharTests(unittest.TestCase):
    """dict_miss_chars：字级词典覆盖的如实标注（缺什么报什么）。"""

    def test_fully_covered_text_has_no_miss_chars(self):
        self.assertEqual(llm.dict_miss_chars("今天天气真好"), [])
        self.assertEqual(llm.dict_miss_chars("你好"), [])

    def test_uncovered_chars_reported_in_order_unique(self):
        self.assertEqual(llm.dict_miss_chars("量子计算"), ["量", "子", "计", "算"])
        self.assertEqual(llm.dict_miss_chars("量量计计算"), ["量", "计", "算"])

    def test_non_cjk_and_punctuation_ignored(self):
        self.assertEqual(llm.dict_miss_chars("hello 123？"), [])
        self.assertEqual(llm.dict_miss_chars("hello量123"), ["量"])


class DictMissLLMTranslateTests(unittest.TestCase):
    """词典未命中 + allow_llm_translate：只补翻译一层，回答仍不编造。"""

    MISS_TEXT = "量子计算如何影响星际航行？"

    def test_miss_with_flag_uses_llm_translation_only(self):
        with (
            patch.object(llm, "API_KEY", "test-secret"),
            patch.object(llm, "LLM_BASE", "https://example.invalid/v1"),
            patch.object(llm, "LLM_MODEL", "test-model"),
            patch.object(llm, "_call_chat") as call_chat,
            patch.object(llm, "_call_translate",
                         return_value="  算者，穷理尽性也。  ") as call_tr,
        ):
            result = llm.generate_turn(self.MISS_TEXT, mode="dictionary",
                                       allow_llm_translate=True)

        call_chat.assert_not_called()
        call_tr.assert_called_once()
        self.assertEqual(result["source"], "local-dictionary-miss")
        self.assertEqual(result["translation_source"], "llm")
        self.assertEqual(result["translation"], "算者，穷理尽性也。")
        self.assertEqual(result["reply"], "")
        self.assertEqual(result["reply_modern"], "")
        self.assertTrue(result["dict_translation"])
        self.assertEqual(result["missed_chars"],
                         llm.dict_miss_chars(self.MISS_TEXT))

    def test_miss_without_flag_never_calls_llm(self):
        with (
            patch.object(llm, "API_KEY", "test-secret"),
            patch.object(llm, "_call_chat") as call_chat,
            patch.object(llm, "_call_translate") as call_tr,
        ):
            result = llm.generate_turn(self.MISS_TEXT, mode="dictionary")

        call_chat.assert_not_called()
        call_tr.assert_not_called()
        self.assertEqual(result["source"], "local-dictionary-miss")
        self.assertEqual(result["translation_source"], "dictionary")
        self.assertEqual(result["translation"],
                         llm.simple_translate(self.MISS_TEXT))
        self.assertEqual(result["reply"], "")

    def test_llm_translation_failure_keeps_dictionary_translation(self):
        with (
            patch.object(llm, "API_KEY", "test-secret"),
            patch.object(llm, "_call_translate",
                         side_effect=RuntimeError("offline")) as call_tr,
        ):
            result = llm.generate_turn(self.MISS_TEXT, mode="dictionary",
                                       allow_llm_translate=True)

        call_tr.assert_called_once()
        self.assertEqual(result["translation_source"], "dictionary")
        self.assertEqual(result["translation"],
                         llm.simple_translate(self.MISS_TEXT))
        self.assertEqual(result["reply"], "")

    def test_miss_with_flag_but_no_key_stays_dictionary(self):
        with (
            patch.object(llm, "API_KEY", ""),
            patch.object(llm, "_call_translate") as call_tr,
        ):
            result = llm.generate_turn(self.MISS_TEXT, mode="dictionary",
                                       allow_llm_translate=True)

        call_tr.assert_not_called()
        self.assertEqual(result["translation_source"], "dictionary")
        self.assertEqual(result["source"], "local-dictionary-miss")

    def test_canned_reply_hit_does_not_invoke_llm_translation(self):
        # 「故事」命中预设应答 → 属于命中路径，即便有缺字也不走 LLM
        with (
            patch.object(llm, "API_KEY", "test-secret"),
            patch.object(llm, "_call_translate") as call_tr,
        ):
            result = llm.generate_turn("讲讲量子故事", mode="dictionary",
                                       allow_llm_translate=True)

        call_tr.assert_not_called()
        self.assertEqual(result["source"], "local-dictionary")
        self.assertEqual(result["translation_source"], "dictionary")
        self.assertTrue(result["reply"])

    def test_api_success_labels_translation_source_llm(self):
        with (
            patch.object(llm, "API_KEY", "test-secret"),
            patch.object(llm, "_call_chat",
                         return_value=dict(MODEL_REPLY)) as call,
        ):
            result = llm.generate_turn("今天天气怎么样？", mode="api")

        call.assert_called_once()
        self.assertEqual(result["source"], "cloud")
        self.assertEqual(result["translation_source"], "llm")

    def test_api_failure_fallback_does_not_call_translate(self):
        # API 失败回退词典时不再向同一端点发起第二次 LLM 调用
        with (
            patch.object(llm, "API_KEY", "test-secret"),
            patch.object(llm, "_call_chat",
                         side_effect=ConnectionError("offline")),
            patch.object(llm, "_call_translate") as call_tr,
        ):
            result = llm.generate_turn(self.MISS_TEXT, mode="api",
                                       allow_llm_translate=True)

        call_tr.assert_not_called()
        self.assertEqual(result["source"], "local-dictionary-miss")
        self.assertEqual(result["translation_source"], "dictionary")


class DictTranslateCallTests(unittest.TestCase):
    def test_translate_request_uses_dedicated_prompt_and_proxy_policy(self):
        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": "河汉清浅。"},
                                     "finish_reason": "stop"}]}

        with patch.object(llm.httpx, "post",
                          return_value=_Resp()) as post:
            out = llm._call_translate("http://192.168.1.20:8080/v1", "m",
                                      "今天天气真好")

        self.assertEqual(out, "河汉清浅。")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["messages"][0]["role"], "user")
        self.assertIn("文言文", payload["messages"][0]["content"])
        # 局域网端点不走公网代理（与 _call_chat 同一策略）
        self.assertFalse(post.call_args.kwargs["trust_env"])

    def test_translate_truncated_output_raises(self):
        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": "河汉"},
                                     "finish_reason": "length"}]}

        with patch.object(llm.httpx, "post", return_value=_Resp()):
            with self.assertRaises(RuntimeError):
                llm._call_translate("http://127.0.0.1:9/v1", "m", "今天")


class TurnEngineTranslationSourceTests(unittest.TestCase):
    def test_make_turn_carries_translation_source(self):
        import language.turn_engine as te
        with patch.object(
            te.llm_client, "generate_turn",
            return_value={"translation": "今日天象甚佳",
                          "reply": "", "reply_modern": "",
                          "source": "local-dictionary-miss",
                          "translation_source": "llm"},
        ):
            turn = te.make_turn("今天天气真好", mode=te.MODE_ANCIENT)

        self.assertEqual(turn.translation_source, "llm")
        self.assertEqual(turn.source, "local-dictionary-miss")
        self.assertEqual(turn.reply, "")


if __name__ == "__main__":
    unittest.main()
