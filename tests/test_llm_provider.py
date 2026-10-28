"""Tests for the two supported LLM routes: API and local dictionary."""
import json
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


if __name__ == "__main__":
    unittest.main()
