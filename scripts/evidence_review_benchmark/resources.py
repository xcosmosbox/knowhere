"""Explicit lab-only resource intervention, never a production default.

Provider-max profiles have no episode step/deadline, correction-step, HTTP wait,
input-size or monetary budget. The sole completion ceiling is DeepSeek's official
393216-token API maximum. One correction/two reviews remain workflow invariants,
not a strategy of retrying until a desired verdict. Source/schema checks remain.
"""
from __future__ import annotations

import hashlib
import math
import os
import sys
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from runtime import BASE_URL, MODEL

PROFILES = ("production", "provider-max-thinking", "provider-max-nonthinking")
PROVIDER_MAX_TOKENS = 393216


def resource_spec(profile: str) -> dict[str, Any]:
    if profile not in PROFILES:
        raise ValueError("Unknown resource profile")
    if profile == "production":
        return {"profile": profile, "thinking": "disabled", "reasoning_effort": None,
                "episode_steps": 15, "episode_seconds": 180, "outer_seconds": 210,
                "completion_tokens": 1024, "scorer_completion_tokens": 2048,
                "review_seconds": 30, "correction_steps": 4}
    return {"profile": profile,
            "thinking": "enabled" if profile.endswith("-thinking") else "disabled",
            "reasoning_effort": "max" if profile.endswith("-thinking") else None,
            "episode_steps": None, "episode_seconds": None, "outer_seconds": None,
            "completion_tokens": PROVIDER_MAX_TOKENS,
            "scorer_completion_tokens": PROVIDER_MAX_TOKENS, "review_seconds": None,
            "correction_steps": None, "monetary_budget": None,
            "thinking_tool_choice_policy": "Thinking mode rejects named/required choices. A sole named pick tool uses auto; production pick validation and read/pick permissions remain unchanged. Non-thinking keeps the native named choice.",
            "source": "https://api-docs.deepseek.com/api/create-chat-completion",
            "interpretation": "Explicit experimental resource intervention; not production defaults or historical 15-step results. null means no local limit. Natural finish/error/cancellation ends an episode; failed or invalid calls are not retried."}


def tokenizer_identity() -> dict[str, Any]:
    from shared.utils import text_utils
    if text_utils._blingfire_text_to_words is None:
        return {"english_backend": "syntok", "native_library_sha256": None}
    import blingfire
    path = Path(blingfire.__file__).parent / (
        "libblingfiretokdll.dylib" if sys.platform == "darwin" else "libblingfiretokdll.so")
    return {"english_backend": "blingfire", "native_library_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def request_options(profile: str) -> dict[str, Any]:
    spec = resource_spec(profile)
    if profile == "production":
        raise ValueError("The production profile must use the existing production adapter")
    options = {"max_tokens": PROVIDER_MAX_TOKENS, "timeout": None,
               "extra_body": {"thinking": {"type": spec["thinking"]}}}
    if spec["thinking"] == "enabled":
        options["reasoning_effort"] = spec["reasoning_effort"]
    else:
        options["temperature"] = 0
    return options


def _apply_options(kwargs: dict[str, Any], profile: str) -> dict[str, Any]:
    options = {key: value for key, value in kwargs.items()
               if key not in {"temperature", "max_tokens", "timeout", "extra_body", "reasoning_effort"}}
    if resource_spec(profile)["thinking"] == "enabled" and isinstance(options.get("tool_choice"), dict):
        tools = options.get("tools", [])
        choice = options["tool_choice"]
        if len(tools) != 1 or tools[0].get("function", {}).get("name") != choice.get("function", {}).get("name"):
            raise ValueError("Thinking requires auto selection; only a sole-tool pick phase is supported")
        options["tool_choice"] = "auto"
    return {**options, **request_options(profile)}


class _ExplorerClient:
    def __init__(self, profile: str):
        from openai import OpenAI
        from shared.services.http.client_pool import get_sync_client
        self.profile = profile
        self.client = OpenAI(api_key=os.environ["DS_KEY"], base_url=BASE_URL,
                             timeout=None, max_retries=0, http_client=get_sync_client())

    def chat_completion_raw_with_usage(self, **kwargs: Any):
        from shared.services.ai.token_tracking import record_tokens
        from shared.services.ai.openai_compatible_client_sync import _extract_usage
        response = self.client.chat.completions.create(**_apply_options(kwargs, self.profile))
        usage = _extract_usage(response)
        record_tokens(usage, model=MODEL, task="benchmark.unrestricted_explorer")
        return response, usage


def scorer_client(client: Any, profile: str) -> Any:
    if profile == "production":
        return client
    client = client.with_options(timeout=None, max_retries=0)
    async def create(**kwargs):
        return await client.chat.completions.create(**_apply_options(kwargs, profile))
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def install(profile: str) -> ExitStack:
    """Patch only this benchmark process; restore all production objects on exit."""
    stack = ExitStack()
    if profile == "production":
        return stack
    resource_spec(profile)  # Validate before mutating anything.
    from shared.services.retrieval.agent_explore import budget as budget_module
    from shared.services.retrieval.agent_explore import evidence_review as review
    from shared.services.retrieval.agent_explore.harness import openai_harness as harness
    from shared.services.retrieval.agent_tools import ToolBudget

    class UnrestrictedBudget(budget_module.EpisodeBudget):
        benchmark_resource_profile = profile
        def __init__(self, **kwargs):
            super().__init__(**{**kwargs, "max_steps": sys.maxsize, "wall_clock_seconds": math.inf})

    async def reviewer(messages, max_tokens):
        from openai import AsyncOpenAI
        from shared.services.http.client_pool import get_async_client
        from shared.services.ai.token_tracking import record_tokens
        client = AsyncOpenAI(api_key=os.environ["DS_KEY"], base_url=BASE_URL,
                             timeout=None, max_retries=0, http_client=get_async_client())
        response = await client.chat.completions.create(model=MODEL, messages=messages,
            response_format={"type": "json_object"}, **request_options(profile))
        usage = response.usage.model_dump() if response.usage is not None else None
        if usage is not None:
            record_tokens(usage, model=MODEL, task="agent_explore.evidence_review")
        if len(response.choices) != 1:
            raise review._ReviewFailure("The reviewer returned no unique assessment.", usage)
        choice = response.choices[0]
        if choice.finish_reason != "stop" or getattr(choice.message, "refusal", None) or choice.message.tool_calls:
            raise review._ReviewFailure("The reviewer response was incomplete or refused.", usage)
        return choice.message.content or "", usage

    stack.enter_context(patch.object(budget_module, "EpisodeBudget", UnrestrictedBudget))
    stack.enter_context(patch.object(harness, "_resolve_client_and_model",
                                    lambda **kwargs: (_ExplorerClient(profile), MODEL)))
    stack.enter_context(patch.object(harness, "AGENT_EXPLORE_MAX_COMPLETION_TOKENS", PROVIDER_MAX_TOKENS))
    stack.enter_context(patch.object(harness, "render_budget", lambda budget: f"steps used: {budget.steps_used}; no preset step or time ceiling"))
    stack.enter_context(patch.object(harness, "ToolBudget", lambda: ToolBudget(max_chars=sys.maxsize, max_items=sys.maxsize)))
    stack.enter_context(patch.object(review, "_default_reviewer", reviewer))
    stack.enter_context(patch.object(review, "MAX_REVIEW_SECONDS", math.inf))
    stack.enter_context(patch.object(review, "MAX_CORRECTION_STEPS", sys.maxsize))
    stack.enter_context(patch.object(review, "MAX_REVIEW_OUTPUT_TOKENS", PROVIDER_MAX_TOKENS))
    stack.enter_context(patch.object(review, "MAX_REVIEW_INPUT_BYTES", sys.maxsize))
    stack.enter_context(patch.object(review, "_SYSTEM_PROMPT", review._SYSTEM_PROMPT.replace(
        "Keep the response within 1024 tokens.", "Return the complete required JSON schema.")))
    return stack
