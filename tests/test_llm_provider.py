"""Tests for selecting local, cloud, and rules-only LLM modes."""
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


class LLMProviderTests(unittest.TestCase):
    def test_private_lan_model_endpoint_bypasses_proxy_environment(self):
        with patch.object(llm.httpx, "post", return_value=_FakeResponse()) as post:
            llm._call_chat(
                "http://192.168.1.20:8080/v1", "test-model", "你好", []
            )
        self.assertFalse(post.call_args.kwargs["trust_env"])

    def test_public_model_endpoint_can_use_proxy_environment(self):
        with patch.object(llm.httpx, "post", return_value=_FakeResponse()) as post:
            llm._call_chat(
                "https://api.example.invalid/v1", "test-model", "你好", []
            )
        self.assertTrue(post.call_args.kwargs["trust_env"])

    def test_cloud_mode_skips_local_model_entirely(self):
        with (
            patch.object(llm, "LLM_PROVIDER", "cloud"),
            patch.object(llm, "API_KEY", "test-secret"),
            patch.object(llm, "LLM_BASE", "https://example.invalid/v1"),
            patch.object(llm, "LLM_MODEL", "test-model"),
            patch.object(llm, "_call_chat", return_value=dict(MODEL_REPLY)) as call,
        ):
            result = llm.generate_turn("今天天气怎么样？")

        self.assertEqual(result["source"], "cloud")
        self.assertEqual(call.call_count, 1)
        args, kwargs = call.call_args
        self.assertEqual(args[0], "https://example.invalid/v1")
        self.assertEqual(args[1], "test-model")
        self.assertEqual(kwargs["key"], "test-secret")

    def test_auto_tries_cloud_after_local_failure(self):
        with (
            patch.object(llm, "LLM_PROVIDER", "auto"),
            patch.object(llm, "API_KEY", "test-secret"),
            patch.object(llm, "LOCAL_BASE", "http://127.0.0.1:8080/v1"),
            patch.object(llm, "LLM_BASE", "https://example.invalid/v1"),
            patch.object(llm, "_call_chat",
                         side_effect=[ConnectionError("no local model"),
                                      dict(MODEL_REPLY)]) as call,
        ):
            result = llm.generate_turn("请作答")

        self.assertEqual(result["source"], "cloud")
        self.assertEqual(call.call_count, 2)
        self.assertEqual(call.call_args_list[0].args[0],
                         "http://127.0.0.1:8080/v1")
        self.assertEqual(call.call_args_list[1].args[0],
                         "https://example.invalid/v1")

    def test_local_mode_does_not_call_cloud_after_failure(self):
        with (
            patch.object(llm, "LLM_PROVIDER", "local"),
            patch.object(llm, "API_KEY", "test-secret"),
            patch.object(llm, "_call_chat",
                         side_effect=ConnectionError("no endpoint")) as call,
        ):
            result = llm.generate_turn("你好")

        self.assertEqual(result["source"], "local-rules")
        self.assertEqual(call.call_count, 1)

    def test_cloud_mode_without_key_uses_rules_without_local_attempt(self):
        with (
            patch.object(llm, "LLM_PROVIDER", "cloud"),
            patch.object(llm, "API_KEY", ""),
            patch.object(llm, "_call_chat") as call,
        ):
            result = llm.generate_turn("你好")

        self.assertEqual(result["source"], "local-rules")
        call.assert_not_called()

    def test_rules_mode_never_calls_any_model_endpoint(self):
        with (
            patch.object(llm, "LLM_PROVIDER", "rules"),
            patch.object(llm, "_call_chat") as call,
        ):
            result = llm.generate_turn("你好")

        self.assertEqual(result["source"], "local-rules")
        call.assert_not_called()

    def test_local_mode_uses_configured_remote_compatible_endpoint(self):
        with (
            patch.object(llm, "LLM_PROVIDER", "local"),
            patch.object(llm, "LOCAL_BASE", "http://192.168.1.20:8080/v1"),
            patch.object(llm, "LOCAL_MODEL", "my-model"),
            patch.object(llm, "LOCAL_API_KEY", "internal-key"),
            patch.object(llm, "_call_chat", return_value=dict(MODEL_REPLY)) as call,
        ):
            result = llm.generate_turn("请作答")

        self.assertEqual(result["source"], "local-model")
        self.assertEqual(call.call_count, 1)
        self.assertEqual(call.call_args.args[0], "http://192.168.1.20:8080/v1")
        self.assertEqual(call.call_args.args[1], "my-model")
        self.assertEqual(call.call_args.kwargs["key"], "internal-key")


if __name__ == "__main__":
    unittest.main()
