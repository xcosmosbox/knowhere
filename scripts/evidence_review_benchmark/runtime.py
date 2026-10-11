"""Benchmark-only configuration and passive HTTP usage observation.

The application transport, prompts, retries and response handling stay intact.
No request headers or credentials are retained in the observation records.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from contextvars import ContextVar
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MODEL = "deepseek-flash"
BASE_URL = "https://api.deepseek.com/v1"


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def prepare_environment(key_file: Path | None = None) -> None:
    sys.path.insert(0, str(ROOT / "packages/shared-python"))
    if key_file is not None:
        os.environ["DS_KEY"] = key_file.read_text().strip()
    if not os.environ.get("DS_KEY"):
        raise ValueError("DS_KEY or --key-file is required")
    os.environ["DS_URL"] = BASE_URL
    os.environ["LLM_MOCK_ENABLED"] = "false"
    os.environ["AGENT_EXPLORE_HARNESS"] = "openai"
    for key, value in {
        "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
        "TMP_PATH": "/tmp/knowhere-evidence-experiment",
        "S3_BUCKET_NAME": "benchmark-unused",
        "S3_ACCESS_KEY_ID": "benchmark-unused",
        "S3_SECRET_ACCESS_KEY": "benchmark-unused",
        "S3_TEMP_PATH": "/tmp",
    }.items():
        os.environ.setdefault(key, value)


def provider_override() -> dict[str, str]:
    return {"api_key": os.environ["DS_KEY"], "base_url": BASE_URL, "model": MODEL}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProviderObserver:
    """Non-streaming completion metadata; real returned model/usage are authoritative."""

    def __init__(self, events_path: Path | None = None) -> None:
        self.records: list[dict[str, Any]] = []
        self._trial_id: ContextVar[str] = ContextVar("benchmark_trial_id", default="setup")
        self.events_path = events_path

    def emit(self, record: dict[str, Any]) -> None:
        if self.events_path is None:
            return
        safe = {key: value for key, value in record.items() if key not in {"review_input", "review_output"}}
        with self.events_path.open("a") as stream:
            stream.write(json.dumps(safe) + "\n")
            stream.flush()

    @property
    def trial_id(self) -> str:
        return self._trial_id.get()

    @trial_id.setter
    def trial_id(self, value: str) -> None:
        self._trial_id.set(value)

    def request(self, request: Any) -> None:
        if request.url.host != "api.deepseek.com" or not request.url.path.endswith("/chat/completions"):
            return
        payload = json.loads(request.content)
        messages = payload.get("messages", [])
        system = str(messages[0].get("content", "")) if messages else ""
        reviewer = system.startswith("You independently assess whether")
        semantic = system.startswith("You are a blinded external evidence assessor")
        record = {
            "call_id": len(self.records), "trial_id": self.trial_id,
            "kind": "reviewer" if reviewer else ("semantic_evaluator" if semantic else "explorer"),
            "requested_model": payload.get("model"), "started_at": utc_now(),
            "prompt_sha256": digest(messages), "request_sha256": digest(payload),
            "temperature": payload.get("temperature"), "max_tokens": payload.get("max_tokens"),
            "thinking": payload.get("thinking"), "tool_choice": payload.get("tool_choice"),
            "reasoning_effort": payload.get("reasoning_effort"),
            "transport_timeout": request.extensions.get("timeout"),
            "status": "no_response", "usage": None,
        }
        from resources import ACTIVE_SCOPE
        scope = ACTIVE_SCOPE.get()
        if scope is not None and not reviewer and not semantic:
            record["source_scope_accounting"] = scope.report()
        if reviewer:
            # Contains only the exact evidence sent to the production reviewer.
            record["review_input"] = json.loads(messages[-1]["content"])
        request.extensions["benchmark_observation"] = (record, time.perf_counter())
        self.records.append(record)
        self.emit(record)

    def response(self, response: Any) -> None:
        observation = response.request.extensions.get("benchmark_observation")
        if observation is None:
            return
        record, started = observation
        record.update(status="response", http_status=response.status_code,
                      duration_ms=round((time.perf_counter() - started) * 1000, 3), ended_at=utc_now())
        try:
            data = response.json()
        except (ValueError, UnicodeDecodeError):
            record["status"] = "non_json_response"
            return
        record.update(returned_model=data.get("model"), usage=data.get("usage"),
                      finish_reasons=[choice.get("finish_reason") for choice in data.get("choices", [])])
        if record["kind"] == "explorer":
            record["tool_calls"] = [call for choice in data.get("choices", [])
                                    for call in choice.get("message", {}).get("tool_calls", [])]
        # No error strings, headers, or request credentials are serialized.
        if record["kind"] == "reviewer":
            record["review_output"] = [choice.get("message", {}).get("content") for choice in data.get("choices", [])]
        self.emit(record)

    def sync_response(self, response: Any) -> None:
        response.read()
        self.response(response)

    async def async_request(self, request: Any) -> None:
        self.request(request)

    async def async_response(self, response: Any) -> None:
        await response.aread()
        self.response(response)

    def install(self) -> None:
        from shared.services.http.client_pool import get_async_client, get_sync_client
        self.sync_client, self.async_client = get_sync_client(), get_async_client()
        self.sync_client.event_hooks["request"].append(self.request)
        self.sync_client.event_hooks["response"].append(self.sync_response)
        self.async_client.event_hooks["request"].append(self.async_request)
        self.async_client.event_hooks["response"].append(self.async_response)

    async def close(self) -> None:
        from shared.services.http.client_pool import close_async_client, close_sync_client
        await close_async_client()
        close_sync_client()


class EpisodeObserver:
    """Pass-through observers; never substitute a model, tool, or snapshot."""

    def __init__(self) -> None:
        self.snapshots: list[dict[str, Any]] = []
        self.episode: dict[str, Any] = {}

    def install(self) -> None:
        from shared.services.retrieval.agent_explore.harness.openai_harness import OpenAIHarness
        from shared.services.retrieval.execution import evidence_review
        self.harness = OpenAIHarness
        self.snapshot_module = evidence_review
        self.original_episode = OpenAIHarness.run_episode
        self.original_snapshot = evidence_review.build_review_snapshot
        observer = self

        async def run_episode(instance: Any, **kwargs: Any) -> Any:
            budget = kwargs["budget"]
            unrestricted = getattr(budget, "benchmark_resource_profile", None)
            observer.episode = {"initial_max_steps": None if unrestricted else budget.max_steps,
                                "initial_wall_clock_seconds": None if unrestricted else budget.wall_clock_seconds}
            if unrestricted:
                observer.episode["resource_profile"] = unrestricted
            started = time.perf_counter()
            try:
                result = await observer.original_episode(instance, **kwargs)
                observer.episode.update(stop_reason=result.stop_reason, model=result.model_name,
                                        steps=[asdict(step) for step in result.steps],
                                        pool=[asdict(candidate) for candidate in result.pool])
                return result
            finally:
                from resources import ACTIVE_SCOPE
                scope = ACTIVE_SCOPE.get()
                if scope is not None and unrestricted == "provider-max-scoped-thinking":
                    observer.episode["source_scope_accounting"] = scope.report()
                observer.episode.update(steps_used=budget.steps_used, tokens_used=budget.tokens_used,
                                        usage_complete=budget.usage_complete,
                                        final_max_steps=None if unrestricted else budget.max_steps,
                                        duration_ms=round((time.perf_counter() - started) * 1000, 3))

        def build_snapshot(**kwargs: Any) -> Any:
            snapshot = observer.original_snapshot(**kwargs)
            observer.snapshots.append(asdict(snapshot))
            return snapshot

        OpenAIHarness.run_episode = run_episode
        evidence_review.build_review_snapshot = build_snapshot

    def restore(self) -> None:
        self.harness.run_episode = self.original_episode
        self.snapshot_module.build_review_snapshot = self.original_snapshot


def usage_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    fields = ("prompt_tokens", "completion_tokens", "total_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens")
    complete = all(isinstance(row.get("usage"), dict) and all(isinstance(row["usage"].get(key), int) for key in fields) for row in records)
    totals = {key: sum((row.get("usage") or {}).get(key, 0) or 0 for row in records) for key in fields}
    return {"calls": len(records), "usage_complete": complete,
            "returned_models": sorted({row["returned_model"] for row in records if row.get("returned_model")}),
            "observed_tokens": totals, "complete_tokens": totals if complete else None}
