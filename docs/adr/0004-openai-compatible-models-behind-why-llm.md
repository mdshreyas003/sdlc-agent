---
status: accepted
---

# Every model step can run on an OpenAI-compatible server, picked by `WHY_LLM`

Until now every model step went to Anthropic: Decision extraction (Sonnet 5.5), the composer, entity matching and the Supersession judge (Opus 5.5), plus the scoreboard's baselines and judge. We want to run everything without an Anthropic key, on Sarvam (`sarvam-105b`) or any other OpenAI-compatible server (vLLM, OpenRouter). So `WHY_LLM=openai` sends every step, the product's and the scoreboard's, to `OPENAI_BASE_URL` (default `https://api.sarvam.ai/v1`) with `OPENAI_API_KEY`, all on one model, `WHY_OPENAI_MODEL` (default `sarvam-105b`). `WHY_LLM=anthropic` stays the default and behaves exactly as before.

The switch lives at the one call every step already makes: the structured call picks the API by the SDK client it is given, so the domain adapters (the `Anthropic*` proposer, composer, matcher and judge classes) are unchanged and keep their names. The scoreboard gains `OpenAIStructured` and `OpenAIToolLoop` beside the Anthropic ones.

## Considered Options

- **Replace Anthropic outright.** Would mean rewriting the Anthropic tests and losing the configuration earlier results were made with.
- **LiteLLM or another adapter library.** Another layer for no gain: the official `openai` SDK already reaches any OpenAI-compatible server through `base_url`, and Anthropic-only features (prompt caching, `effort`) do not translate through an adapter either.
- **Sarvam's V2 endpoint.** Its docs leave structured output unspecified for the open-weight models; V1 documents strict `json_schema` output.

## Consequences

- No prompt caching on the OpenAI path (no OpenAI-style equivalent). Our own disk cache of responses still makes rebuilds reproducible; its key includes the model, so Claude and Sarvam responses never mix.
- `effort` is sent as `reasoning_effort`. Sarvam counts reasoning tokens against `max_tokens` (kept at 16000); a reply cut off there is a `LlmError`, exactly like a truncated Claude reply, and the reasoning text is never read.
- Cost is unknown for non-Claude models (no entry in `PRICES`); token counts are still recorded.
- With `WHY_LLM=openai` the scoreboard's judge is Sarvam too. Its agreement with the hand labels must be measured again (`whycode-eval agreement`) before scores are trusted, and those scores are not comparable with runs judged by Opus.
- Out of scope: the agent comparison (`whycode-agents`), which benchmarks Claude Code itself.
- `WHY_COMPOSER=anthropic` / `WHY_EXTRACTOR=anthropic` / the `anthropic` judge now mean "the model step" rather than the vendor; `WHY_LLM` names the vendor. Renaming those values is left for later.
