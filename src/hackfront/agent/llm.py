"""Provider-agnostic LLM layer.

The agent needs one thing from a model: a chat completion. `LLMClient` is that interface; `OpenAICompatibleClient`
implements it over the OpenAI Python SDK (any server speaking the OpenAI chat-completions API: OpenAI, Azure OpenAI /
Foundry `/openai/v1/`, Sarvam, OpenRouter, vLLM, Ollama, LM Studio, ...). Providers are presets of that one client:

- `openai`: generic OpenAI-compatible endpoint, configured only from the environment
  (LLM_API_KEY, LLM_MODEL, optional LLM_BASE_URL; LLM_TIMEOUT optional).
- `azure`, `sarvam`: legacy presets kept for backward compatibility (AZURE_FOUNDRY_ENDPOINT + AZURE_FOUNDRY_API_KEY,
  SARVAM_API_KEY); their keys may also live in a workspace's secret store.

LLM_PROVIDER picks the default provider; otherwise the first configured one is used. Clients are built lazily, cached
per provider and rebuilt when credentials change. Tests inject doubles into `_clients`: either an `LLMClient` or an
object shaped like the SDK (`.chat.completions.create(...)`), which is wrapped in `OpenAICompatibleClient`.
"""

from __future__ import annotations

import json
import logging
import os
import re
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlsplit

from pydantic import BaseModel, ValidationError

from .. import config

log = logging.getLogger(__name__)

MAX_TOKENS = 16000  # default for LLM_MAX_TOKENS; Sarvam spends part of this on reasoning_content, which we ignore
MAX_TOKENS_PARAMS = ("max_tokens", "max_completion_tokens")  # LLM_MAX_TOKENS_PARAM; reasoning models want the latter
DEFAULT_TIMEOUT = 180.0
SARVAM_URL = "https://api.sarvam.ai/v1/"
GENERIC = "openai"
_GENERIC_HINT = "set LLM_API_KEY and LLM_MODEL (plus LLM_BASE_URL for any endpoint other than api.openai.com)"


class LLMConfigError(RuntimeError):
    """The selected provider is not fully configured. The message names env vars, never values."""


class UnknownProviderError(LLMConfigError, ValueError):
    """A provider name outside PROVIDERS (also a ValueError, as before the provider layer)."""


@dataclass(frozen=True)
class Completion:
    text: str  # raw message content (may include <think> blocks; callers use clean())
    total_tokens: int = 0


@runtime_checkable
class LLMClient(Protocol):
    """What the agent calls on a model: one chat completion."""

    def complete(self, messages: list[dict[str, str]], *, model: str, max_tokens: int) -> Completion: ...


class OpenAICompatibleClient:
    """`LLMClient` over the OpenAI SDK chat-completions surface (or any object shaped like it)."""

    def __init__(self, sdk: Any, max_tokens_param: str = "max_tokens"):
        self.sdk = sdk
        self.max_tokens_param = max_tokens_param  # name of the output-limit argument this endpoint accepts

    @classmethod
    def connect(cls, *, api_key: str, base_url: str | None, headers: dict[str, str] | None = None,
                timeout: float = DEFAULT_TIMEOUT, max_tokens_param: str = "max_tokens") -> OpenAICompatibleClient:
        from openai import OpenAI

        sdk = OpenAI(base_url=base_url, api_key=api_key, default_headers=headers or None, timeout=timeout)
        return cls(sdk, max_tokens_param)

    def complete(self, messages: list[dict[str, str]], *, model: str, max_tokens: int) -> Completion:
        limit = {self.max_tokens_param: max_tokens}
        resp = self.sdk.chat.completions.create(model=model, messages=messages, **limit)
        used = getattr(getattr(resp, "usage", None), "total_tokens", 0)
        return Completion(text=resp.choices[0].message.content or "", total_tokens=used if isinstance(used, int) else 0)


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    key_env: str  # env var named in "not configured" errors
    key_setting: str | None  # config.SECRETS key (workspace store, env fallback); None = environment only
    default_model: str
    base_url: str | None = None  # fixed URL; None = derived (azure) or LLM_BASE_URL / SDK default (openai)
    key_header: str | None = None  # extra auth header some providers read instead of Authorization: Bearer


PROVIDERS: dict[str, ProviderSpec] = {
    "azure": ProviderSpec("azure", "AZURE_FOUNDRY_API_KEY", "azure_key", "Kimi-K2.5", key_header="api-key"),
    "sarvam": ProviderSpec("sarvam", "SARVAM_API_KEY", "sarvam_key", "sarvam-105b", SARVAM_URL,
                           "api-subscription-key"),  # alternative model: sarvam-30b
    GENERIC: ProviderSpec(GENERIC, "LLM_API_KEY", None, ""),
}

_clients: dict[str, Any] = {}  # provider -> client; rebuilt when credentials change; tests inject fakes here
_creds: dict[str, tuple] = {}  # provider -> (credentials, client) it was built with
TOKENS = [0]  # running total of completion usage; the benchmark reads deltas per question
_workspace: ContextVar[str | None] = ContextVar("llm_workspace", default=None)


def foundry_base_url(endpoint: str) -> str:
    """Any URL Foundry shows (project, /models, /openai/deployments/...?api-version=) -> <resource root>/openai/v1/."""
    parts = urlsplit(endpoint.strip())
    if parts.netloc.endswith(".models.ai.azure.com"):  # serverless (pay-as-you-go) endpoint
        return f"{parts.scheme}://{parts.netloc}/v1/"
    return f"{parts.scheme}://{parts.netloc}/openai/v1/"


def set_workspace(slug: str | None) -> None:
    """Resolve credentials from this workspace's store (env fallback); None = environment only."""
    _workspace.set(slug)


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _setting(key: str) -> str:
    """A config.SECRETS key: workspace store then env when a workspace is set, else env only."""
    slug = _workspace.get()
    value = config.get_secret(slug, key) if slug else os.environ.get(config.SECRETS[key][0])
    return (value or "").strip()


def _from_workspace(key: str) -> bool:
    """True when the active workspace's own store supplies `key` (not the environment fallback)."""
    slug = _workspace.get()
    return bool(slug) and config.secret_status(slug)[key]["source"] == "workspace"


def _spec(provider: str) -> ProviderSpec:
    try:
        return PROVIDERS[provider]
    except KeyError:
        raise UnknownProviderError(f"unknown provider {provider!r}; choose one of {sorted(PROVIDERS)}") from None


def _key(provider: str) -> str:
    spec = _spec(provider)
    # The generic key is environment-only, so a workspace can never redirect it to another host.
    return _setting(spec.key_setting) if spec.key_setting else _env(spec.key_env)


def _base_url(provider: str) -> str | None:
    spec = _spec(provider)
    if provider == "azure":
        endpoint = _setting("azure_endpoint")
        return foundry_base_url(endpoint) if endpoint else None
    if provider == GENERIC:
        return _env("LLM_BASE_URL") or None  # None = SDK default (https://api.openai.com/v1)
    return spec.base_url


def missing_config(provider: str) -> str | None:
    """Why `provider` cannot be used, or None when it is fully configured."""
    spec = _spec(provider)
    if provider == GENERIC:
        if not _key(provider) or not model_for(provider):
            return f"provider {GENERIC} is not configured: {_GENERIC_HINT}"
        return None
    if not _key(provider):
        return f"provider {provider} is not configured: set {spec.key_env}"
    if provider == "azure" and not _setting("azure_endpoint"):
        return "provider azure is not configured: set AZURE_FOUNDRY_ENDPOINT"
    if provider == "azure" and _from_workspace("azure_endpoint") and not _from_workspace("azure_key"):
        # The server's key may only go to the server-configured endpoint, never to a host a workspace chose.
        return ("provider azure: a workspace-saved endpoint needs a workspace-saved key (azure_key); "
                "the server key is only sent to AZURE_FOUNDRY_ENDPOINT")
    return None


def configured(provider: str) -> bool:
    return missing_config(provider) is None


def _ready(provider: str) -> bool:
    """configured() without resolving the model through default_provider() (avoids recursion)."""
    if not _key(provider):
        return False
    if provider == "azure":
        return missing_config("azure") is None  # needs the endpoint; never reads the model
    if provider == GENERIC:
        return bool(_env("LLM_MODEL"))
    return True


def default_provider() -> str:
    """LLM_PROVIDER (workspace or env), else the first fully configured provider, else the generic one."""
    chosen = _setting("llm_provider")
    return chosen or next((n for n in PROVIDERS if _ready(n)), GENERIC)


def model_for(provider: str, model: str | None = None) -> str:
    spec = _spec(provider)
    if model:
        return model
    # llm_model names a model for the default provider only; another provider uses its own default.
    configured_model = _setting("llm_model") if provider == default_provider() else ""
    if provider == GENERIC and not configured_model:
        configured_model = _env("LLM_MODEL")  # the generic provider has no preset model
    return configured_model or spec.default_model


def providers(workspace: str | None = None) -> list[dict]:
    token = _workspace.set(workspace) if workspace else None
    try:
        return [{"name": n, "model": model_for(n), "configured": configured(n)} for n in PROVIDERS]
    finally:
        if token:
            _workspace.reset(token)


def _timeout() -> float:
    raw = _env("LLM_TIMEOUT")
    if not raw:
        return DEFAULT_TIMEOUT
    try:
        value = float(raw)
    except ValueError:
        raise LLMConfigError("LLM_TIMEOUT must be a number of seconds") from None
    if value <= 0:
        raise LLMConfigError("LLM_TIMEOUT must be positive")
    return value


def max_tokens() -> int:
    """LLM_MAX_TOKENS (positive int), default MAX_TOKENS."""
    raw = _env("LLM_MAX_TOKENS")
    if not raw:
        return MAX_TOKENS
    try:
        value = int(raw)
    except ValueError:
        raise LLMConfigError("LLM_MAX_TOKENS must be a whole number") from None
    if value <= 0:
        raise LLMConfigError("LLM_MAX_TOKENS must be positive")
    return value


def _max_tokens_param() -> str:
    """LLM_MAX_TOKENS_PARAM: max_tokens (default) or max_completion_tokens."""
    value = _env("LLM_MAX_TOKENS_PARAM") or "max_tokens"
    if value not in MAX_TOKENS_PARAMS:
        raise LLMConfigError(f"LLM_MAX_TOKENS_PARAM must be one of {', '.join(MAX_TOKENS_PARAMS)}")
    return value


def _as_client(obj: Any) -> LLMClient:
    return obj if isinstance(obj, LLMClient) else OpenAICompatibleClient(obj)


def client(provider: str) -> LLMClient:
    """The client for `provider`, built from the workspace store / environment. Raises LLMConfigError if unusable."""
    _spec(provider)
    built = _creds.get(provider)  # (credentials, client) of the client we built
    if provider in _clients and (built is None or built[1] is not _clients[provider]):
        return _as_client(_clients[provider])  # injected (tests): not ours, no credentials to compare
    problem = missing_config(provider)
    if problem:
        raise LLMConfigError(problem)
    key, url, timeout = _key(provider), _base_url(provider), _timeout()
    param = _max_tokens_param()
    creds = (key, url, timeout, param)
    if built is None or built[0] != creds or provider not in _clients:
        header = _spec(provider).key_header
        # The SDK sends Authorization: Bearer; azure and sarvam also read their own header.
        log.debug("building %s LLM client for %s", provider, url or "SDK default base URL")
        _clients[provider] = OpenAICompatibleClient.connect(
            api_key=key, base_url=url, headers={header: key} if header else None, timeout=timeout,
            max_tokens_param=param)
        _creds[provider] = (creds, _clients[provider])
    return _clients[provider]


def ping(provider: str) -> str:
    """One tiny completion; returns reply text or raises RuntimeError with a message safe to show (no keys, no bodies)."""
    import openai

    try:
        resp = client(provider).complete([{"role": "user", "content": "Reply with: ok"}],
                                         model=model_for(provider), max_tokens=32)
        return clean(resp.text) or "ok"
    except RuntimeError:
        raise  # our own messages (not configured / unknown provider)
    except openai.APIStatusError as error:
        raise RuntimeError(f"{provider} rejected the request (HTTP {error.status_code})") from None
    except (openai.APIError, OSError) as error:  # connection / timeout / transport
        log.info("LLM ping to %s failed: %s", provider, type(error).__name__)
        raise RuntimeError(f"could not reach {provider}") from None


def clean(text: str | None) -> str:
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL).strip()


def structured[S: BaseModel](provider: str, template: str, schema: type[S], _model: str | None = None, **fields: Any) -> S:
    """One structured LLM call returning a validated pydantic instance.

    Schema goes in the prompt and output is validated locally (no dependence on json_schema support).
    One repair round-trip on invalid JSON.
    """
    model, limit = model_for(provider, _model), max_tokens()
    messages = [{"role": "user", "content": template.format(**fields)
                 + "\n\nRespond with ONLY a JSON object (no prose, no code fences) matching this JSON Schema:\n"
                 + json.dumps(schema.model_json_schema())}]
    text = ""
    for attempt in range(2):
        resp = client(provider).complete(messages, model=model, max_tokens=limit)
        text = clean(resp.text)
        TOKENS[0] += resp.total_tokens
        try:
            return schema.model_validate_json(text[text.find("{"): text.rfind("}") + 1])
        except ValidationError as error:
            log.warning("%s returned invalid %s (attempt %d); asking for a repair", model, schema.__name__, attempt + 1)
            messages += [{"role": "assistant", "content": text},
                         {"role": "user", "content": f"That JSON was invalid: {error}. Return the corrected JSON only."}]
    raise RuntimeError(f"{model} did not return valid {schema.__name__}: {text[:200]}")
