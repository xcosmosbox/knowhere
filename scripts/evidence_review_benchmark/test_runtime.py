"""Guard observation boundaries that affect experimental cost attribution."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from runtime import ProviderObserver, usage_summary  # noqa: E402


def request() -> httpx.Request:
    return httpx.Request("POST", "https://api.deepseek.com/v1/chat/completions",
                         headers={"Authorization": "Bearer unit-test-secret"},
                         json={"model": "deepseek-flash", "messages": [{"role": "user", "content": "test"}]})


def test_concurrent_tasks_and_worker_threads_keep_their_trial_identity() -> None:
    observer = ProviderObserver()

    async def one(identity: str) -> None:
        observer.trial_id = identity
        await asyncio.sleep(0)
        await asyncio.to_thread(observer.request, request())

    async def run() -> None:
        await asyncio.gather(one("A"), one("B"), one("C"))
        assert observer.trial_id == "setup"

    asyncio.run(run())
    assert sorted(row["trial_id"] for row in observer.records) == ["A", "B", "C"]


def test_observation_never_serializes_authorization_headers(tmp_path: Path) -> None:
    observer = ProviderObserver(tmp_path / "events.jsonl")
    outbound = request()
    observer.request(outbound)
    response = httpx.Response(200, request=outbound, json={
        "model": "deepseek-flash", "choices": [{"finish_reason": "stop"}],
        "usage": {"prompt_tokens": 9, "completion_tokens": 1, "total_tokens": 10,
                  "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 9},
    })
    observer.response(response)
    saved = (tmp_path / "events.jsonl").read_text()
    assert "unit-test-secret" not in saved
    assert "Authorization" not in saved
    assert json.loads(saved.splitlines()[-1])["usage"]["total_tokens"] == 10


def test_missing_or_partial_usage_cannot_be_reported_as_complete_zero_cost() -> None:
    assert usage_summary([{"usage": None}])["complete_tokens"] is None
    assert usage_summary([{"usage": {"total_tokens": 10}}])["usage_complete"] is False
