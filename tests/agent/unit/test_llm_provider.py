"""Provider layer: env parsing, the client factory, and OpenAICompatibleClient over a mocked SDK (no network)."""

from types import SimpleNamespace
from unittest import mock

import pytest
from pydantic import BaseModel

from hackfront.agent import llm

ENV = ("LLM_PROVIDER", "LLM_MODEL", "LLM_API_KEY", "LLM_BASE_URL", "LLM_TIMEOUT",
       "AZURE_FOUNDRY_API_KEY", "AZURE_FOUNDRY_ENDPOINT", "SARVAM_API_KEY")


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setattr(llm, "_clients", {})
    monkeypatch.setattr(llm, "_creds", {})
    for k in ENV:
        monkeypatch.delenv(k, raising=False)


def reply(content, tokens=None):
    usage = SimpleNamespace(total_tokens=tokens) if tokens is not None else None
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))], usage=usage)


class Out(BaseModel):
    a: int


# ------------------------------------------------------------------ config parsing / factory
def test_nothing_configured_defaults_to_generic_with_a_clear_error():
    assert llm.default_provider() == "openai"
    assert not any(p["configured"] for p in llm.providers())
    with pytest.raises(llm.LLMConfigError, match="LLM_API_KEY and LLM_MODEL"):
        llm.client(llm.default_provider())


def test_generic_needs_key_and_model(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    assert llm.missing_config("openai") and "LLM_MODEL" in llm.missing_config("openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")
    assert llm.missing_config("openai") is None
    assert llm.default_provider() == "openai" and llm.model_for("openai") == "gpt-4o-mini"


def test_generic_factory_passes_base_url_key_model_timeout(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_API_KEY", "sk-or-test")
    monkeypatch.setenv("LLM_MODEL", "meta-llama/llama-3.1-8b-instruct")
    monkeypatch.setenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("LLM_TIMEOUT", "30")
    with mock.patch("openai.OpenAI") as sdk:
        c = llm.client("openai")
    sdk.assert_called_once_with(base_url="https://openrouter.ai/api/v1", api_key="sk-or-test",
                                default_headers=None, timeout=30.0)
    assert isinstance(c, llm.LLMClient) and isinstance(c, llm.OpenAICompatibleClient)
    assert llm.model_for("openai") == "meta-llama/llama-3.1-8b-instruct"


def test_generic_without_base_url_uses_sdk_default(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")
    c = llm.client("openai")  # real SDK object, no request is made
    assert str(c.sdk.base_url).startswith("https://api.openai.com/v1")
    assert c.sdk.auth_headers["Authorization"] == "Bearer sk-test"


def test_client_is_cached_and_rebuilt_when_env_changes(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "k1")
    monkeypatch.setenv("LLM_MODEL", "m")
    first = llm.client("openai")
    assert llm.client("openai") is first
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:8001/v1")
    second = llm.client("openai")
    assert second is not first and str(second.sdk.base_url) == "http://localhost:8001/v1/"


@pytest.mark.parametrize("raw", ["soon", "0", "-5"])
def test_bad_timeout_is_a_config_error(monkeypatch, raw):
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "m")
    monkeypatch.setenv("LLM_TIMEOUT", raw)
    with pytest.raises(llm.LLMConfigError, match="LLM_TIMEOUT"):
        llm.client("openai")


def test_unknown_provider_is_config_and_value_error():
    with pytest.raises(llm.LLMConfigError) as e:
        llm.client("nope")
    assert isinstance(e.value, ValueError) and "choose one of" in str(e.value)


def test_azure_needs_endpoint(monkeypatch):
    monkeypatch.setenv("AZURE_FOUNDRY_API_KEY", "k")
    assert not llm.configured("azure")
    with pytest.raises(llm.LLMConfigError, match="AZURE_FOUNDRY_ENDPOINT"):
        llm.client("azure")


def test_legacy_env_still_selects_a_preset(monkeypatch):
    monkeypatch.setenv("SARVAM_API_KEY", "s")
    assert llm.default_provider() == "sarvam" and llm.model_for("sarvam") == "sarvam-105b"


def test_llm_provider_wins_and_generic_key_never_leaks_to_presets(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "generic")
    monkeypatch.setenv("LLM_MODEL", "m")
    monkeypatch.setenv("SARVAM_API_KEY", "s")
    monkeypatch.setenv("LLM_PROVIDER", "sarvam")
    assert llm.default_provider() == "sarvam"
    assert llm.client("sarvam").sdk.api_key == "s" and llm.client("openai").sdk.api_key == "generic"
    assert "generic" not in str(llm.providers())


# ------------------------------------------------------------------ OpenAICompatibleClient over a mocked SDK
def test_complete_maps_sdk_response_and_usage():
    sdk = mock.Mock()
    sdk.chat.completions.create.return_value = reply("hello", tokens=42)
    out = llm.OpenAICompatibleClient(sdk).complete([{"role": "user", "content": "hi"}], model="m", max_tokens=5)
    assert out == llm.Completion("hello", 42)
    sdk.chat.completions.create.assert_called_once_with(model="m", messages=[{"role": "user", "content": "hi"}],
                                                        max_tokens=5)


def test_complete_tolerates_missing_content_and_usage():
    sdk = mock.Mock()
    sdk.chat.completions.create.return_value = reply(None)
    assert llm.OpenAICompatibleClient(sdk).complete([], model="m", max_tokens=1) == llm.Completion("", 0)


def test_structured_through_generic_provider_counts_tokens(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "local-model")
    sdk = mock.Mock()
    sdk.chat.completions.create.return_value = reply('<think>x</think>{"a": 3}', tokens=11)
    with mock.patch("openai.OpenAI", return_value=sdk):
        before = llm.TOKENS[0]
        assert llm.structured("openai", "q {x}", Out, x="?").a == 3
    assert llm.TOKENS[0] - before == 11
    kwargs = sdk.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "local-model" and kwargs["max_tokens"] == llm.MAX_TOKENS


def test_injected_protocol_double_is_used_directly(monkeypatch):
    class Double:
        def __init__(self):
            self.calls = []

        def complete(self, messages, *, model, max_tokens):
            self.calls.append(model)
            return llm.Completion('{"a": 1}', 2)

    d = Double()
    monkeypatch.setitem(llm._clients, "openai", d)
    assert llm.client("openai") is d
    assert llm.structured("openai", "q", Out, "explicit-model").a == 1 and d.calls == ["explicit-model"]


def test_ping_maps_sdk_errors_to_safe_messages(monkeypatch):
    import httpx
    import openai

    req = httpx.Request("POST", "http://llm.test/v1/chat/completions")
    sdk = mock.Mock()
    monkeypatch.setitem(llm._clients, "openai", sdk)
    monkeypatch.setenv("LLM_MODEL", "m")
    sdk.chat.completions.create.side_effect = openai.APIConnectionError(request=req)
    with pytest.raises(RuntimeError, match="^could not reach openai$"):
        llm.ping("openai")
    sdk.chat.completions.create.side_effect = openai.RateLimitError(
        "slow down sk-secret", response=httpx.Response(429, request=req), body=None)
    with pytest.raises(RuntimeError) as e:
        llm.ping("openai")
    assert str(e.value) == "openai rejected the request (HTTP 429)"
    sdk.chat.completions.create.side_effect = None
    sdk.chat.completions.create.return_value = reply("<think>hm</think> ok")
    assert llm.ping("openai") == "ok"
