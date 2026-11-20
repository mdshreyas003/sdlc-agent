"""The real OpenAI SDK over a fake HTTP transport: no network, no key. A `FakeChat` answers chat completion requests
from a script of replies, as an OpenAI-compatible server (Sarvam, vLLM) would, and reports 10 prompt and 5
completion tokens per reply. A reply is a structured payload (the final answer) or a list of tool calls."""

from __future__ import annotations

import json

import httpx2
from openai import DefaultHttpxClient, OpenAI

from whycode.llm import LlmClient


class ToolCalls(list):
    """A scripted reply asking for tools: [(name, arguments), ...]."""


class FakeChat:
    def __init__(self, *replies: dict | ToolCalls, finish_reason: str = "stop"):
        self.replies, self.finish_reason, self.requests = list(replies), finish_reason, []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        reply = self.replies[min(len(self.requests), len(self.replies)) - 1]
        if isinstance(reply, ToolCalls):
            message = {"role": "assistant", "content": None, "tool_calls": [
                {"id": f"call_{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
                for i, (name, args) in enumerate(reply)]}
            finish = "tool_calls"
        else:
            text = json.dumps(reply)
            if self.finish_reason == "length":
                text = text[: len(text) // 2]
            message, finish = {"role": "assistant", "content": text}, self.finish_reason
        return httpx2.Response(200, json={
            "id": "chatcmpl_test", "object": "chat.completion", "created": 0, "model": body["model"],
            "choices": [{"index": 0, "message": message, "finish_reason": finish}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        })


def sdk_for(api: FakeChat) -> OpenAI:
    return OpenAI(api_key="test", base_url="https://api.test/v1", max_retries=0,
                  http_client=DefaultHttpxClient(transport=httpx2.MockTransport(api)))


def client_for(api: FakeChat, cache_dir=None) -> LlmClient:
    return LlmClient(sdk_for(api), cache_dir=cache_dir)
