"""The real Anthropic SDK over a fake HTTP transport: no network, no key. Each `FakeApi` answers every request with
one structured payload, as a model would, and reports 10 input and 5 output tokens."""

from __future__ import annotations

import json

import httpx2
from anthropic import Anthropic, DefaultHttpxClient

from whycode.llm import LlmClient


class FakeApi:
    def __init__(self, payload: dict, stop_reason: str = "end_turn"):
        self.payload, self.stop_reason, self.requests = payload, stop_reason, []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        text = json.dumps(self.payload)
        if self.stop_reason == "max_tokens":
            text = text[: len(text) // 2]
        return httpx2.Response(200, json={
            "id": "msg_test", "type": "message", "role": "assistant", "model": body["model"],
            "content": [{"type": "text", "text": text}], "stop_reason": self.stop_reason, "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 5},
        })


def sdk_for(api: FakeApi) -> Anthropic:
    return Anthropic(api_key="test", base_url="https://api.test", max_retries=0,
                     http_client=DefaultHttpxClient(transport=httpx2.MockTransport(api)))


def client_for(api: FakeApi, cache_dir=None) -> LlmClient:
    return LlmClient(sdk_for(api), cache_dir=cache_dir)
