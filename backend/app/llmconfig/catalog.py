"""Provider and model catalog.

This is the single place a developer adds a new LLM option. Every provider
must expose an OpenAI-compatible chat completions endpoint (``/chat/completions``
is appended to ``base_url`` at request time). To add a model, append one
``ModelOption`` entry and, if the provider is new, one ``Provider`` entry.

The list is intentionally curated, not fetched: only models that accept image
input belong here, because students attach homework photos to chat. Models are
split by purpose:

* ``recommended="chat"`` — the more expensive, higher-quality models. They
  answer user queries, so they must be image-capable.
* ``recommended="memory"`` — cheap (ideally text-only) models powering the
  background memory worker and chat-title generation that runs on every turn.

The OpenRouter entries were picked for best value as of August 2026 — current
leaders are DeepSeek V4 Flash (0731 checkpoint, which added native image +
audio understanding), OpenAI's budget GPT-5.6 Luna, and open-weight vision
models (Xiaomi MiMo-V2.5, Qwen3-VL-32B). Llama models were intentionally left
out after evaluation.

Prices are USD per 1M tokens (input / output). Gemini prices are Google's exact
list prices; OpenRouter prices are market rates that vary by hosting provider,
so they are shown as ranges.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    id: str
    name: str
    base_url: str
    key_url: str  # where users create an API key for this provider


@dataclass(frozen=True)
class ModelOption:
    id: str
    provider: str
    label: str
    tier: str  # "premium" | "standard" | "budget"
    recommended: str  # "chat" | "memory" | "either"
    supports_images: bool
    price_in: str  # USD per 1M input tokens
    price_out: str  # USD per 1M output tokens
    price_note: str  # e.g. "exact list price" or "varies by host"


PROVIDERS: list[Provider] = [
    Provider(
        "gemini", "Google Gemini",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "https://aistudio.google.com/apikey",
    ),
    Provider(
        "openrouter", "OpenRouter",
        "https://openrouter.ai/api/v1",
        "https://openrouter.ai/keys",
    ),
    Provider(
        "openai", "OpenAI",
        "https://api.openai.com/v1",
        "https://platform.openai.com/api-keys",
    ),
    Provider(
        "anthropic", "Anthropic",
        "https://api.anthropic.com/v1",
        "https://console.anthropic.com/settings/keys",
    ),
]

MODEL_OPTIONS: list[ModelOption] = [
    # ── Chat: image-capable, higher quality ────────────────────────────────
    ModelOption(
        "gemini-3.1-pro-preview", "gemini", "Gemini 3.1 Pro (Preview)",
        tier="premium", recommended="chat", supports_images=True,
        price_in="$2.00", price_out="$12.00",
        price_note="exact list price · prompts ≤ 200k tokens",
    ),
    ModelOption(
        "gemini-3.7-flash", "gemini", "Gemini 3.7 Flash",
        tier="standard", recommended="chat", supports_images=True,
        price_in="$0.75", price_out="$3.75",
        price_note="intro price through Dec 31, 2026",
    ),
    ModelOption(
        "deepseek/deepseek-v4-flash-0731", "openrouter", "DeepSeek V4 Flash (open)",
        tier="budget", recommended="either", supports_images=True,
        price_in="~$0.08", price_out="~$0.16", price_note="varies by host",
    ),
    ModelOption(
        "openai/gpt-5.6-luna", "openrouter", "GPT-5.6 Luna",
        tier="budget", recommended="either", supports_images=True,
        price_in="$0.10", price_out="$0.60",
        price_note="varies by host · price cut Jun 2026",
    ),
    ModelOption(
        "xiaomi/mimo-v2.5", "openrouter", "MiMo-V2.5 (open)",
        tier="budget", recommended="either", supports_images=True,
        price_in="$0.14", price_out="$0.28", price_note="varies by host",
    ),
    ModelOption(
        "qwen/qwen3-vl-32b-instruct", "openrouter", "Qwen3-VL 32B (open)",
        tier="budget", recommended="either", supports_images=True,
        price_in="~$0.10", price_out="~$0.42", price_note="varies by host",
    ),
    ModelOption(
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", "openrouter",
        "NVIDIA Nemotron 3 Nano Omni (free)",
        tier="free", recommended="either", supports_images=True,
        price_in="$0", price_out="$0", price_note="free",
    ),
    # ── Memory: cheap, text-only where possible ────────────────────────────
    ModelOption(
        "gemini-3.5-flash-lite", "gemini", "Gemini 3.5 Flash-Lite",
        tier="budget", recommended="memory", supports_images=True,
        price_in="$0.30", price_out="$2.50", price_note="exact list price",
    ),
    ModelOption(
        "qwen/qwen3-14b", "openrouter", "Qwen3 14B (open, text)",
        tier="budget", recommended="memory", supports_images=False,
        price_in="~$0.10", price_out="~$0.25", price_note="varies by host",
    ),
    ModelOption(
        "openrouter/free", "openrouter", "OpenRouter Free",
        tier="free", recommended="memory", supports_images=False,
        price_in="$0", price_out="$0", price_note="free",
    ),
]

PROVIDER_BY_ID: dict[str, Provider] = {p.id: p for p in PROVIDERS}

def get_provider(provider_id: str) -> Provider | None:
    return PROVIDER_BY_ID.get(provider_id)
