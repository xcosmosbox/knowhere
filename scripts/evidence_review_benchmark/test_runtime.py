"""Guard observation boundaries and frozen production budget accounting."""

from __future__ import annotations

import asyncio
import copy
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run import production_budget_within_bounds, scope_receipts_valid  # noqa: E402
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


def test_verified_scope_read_receipts_survive_the_provider_start_journal(tmp_path: Path) -> None:
    from resources import bind_scope
    from shared.services.retrieval.agent_tools import ToolResult
    manifest = {"documents": [{"document_id": "D", "source_file_name": "source.txt",
                              "chunks": [{"chunk_id": "C", "type": "text", "content": "complete body"}]}]}
    observer = ProviderObserver(tmp_path / "events.jsonl")
    with bind_scope(manifest, ["D"]) as scope:
        scope.observe_read(ToolResult(text="complete body", payload={"chunks": [
            {"document_id": "D", "chunk_id": "C", "content": "complete body"}]}))
        observer.request(request())
    receipt = json.loads((tmp_path / "events.jsonl").read_text())["source_scope_accounting"]
    assert receipt["source_units"] == receipt["exact_full_reads"] == 1
    assert receipt["all_scoped_text_read"] is True
    assert receipt["read_units"][0]["document_id"] == "D"
    assert len(receipt["read_units"][0]["content_sha256"]) == 64
    assert "complete body" not in (tmp_path / "events.jsonl").read_text()


@pytest.mark.parametrize("receipts,complete", [([], False),
    ([{"document_id": "D", "chunk_id": "C", "content_sha256": "sha"}], True)])
def test_scope_gate_accepts_exact_frozen_receipts_including_partial_scope(receipts, complete):
    scope = {"source_units": 1, "exact_full_reads": len(receipts), "read_units": receipts,
             "all_scoped_text_read": complete}
    assert scope_receipts_valid(scope, {("D", "C"): "sha"})


@pytest.mark.parametrize("field,value", [
    ("source_units", True), ("source_units", 2), ("exact_full_reads", True),
    ("exact_full_reads", -1), ("exact_full_reads", 2), ("all_scoped_text_read", False),
    ("all_scoped_text_read", 1), ("read_units", None), ("read_units", [None]),
    ("read_units", [{"document_id": "unknown", "chunk_id": "C"}]),
    ("read_units", [{"document_id": [], "chunk_id": "C", "content_sha256": "sha"}]),
    ("read_units", [{"document_id": "D", "chunk_id": "C", "content_sha256": "wrong"}]),
])
def test_scope_gate_rejects_bad_counts_invisible_sources_and_mutated_receipts(field, value):
    scope = {"source_units": 1, "exact_full_reads": 1, "all_scoped_text_read": True,
             "read_units": [{"document_id": "D", "chunk_id": "C", "content_sha256": "sha"}]}
    scope[field] = value
    assert not scope_receipts_valid(scope, {("D", "C"): "sha"})


def test_scope_gate_never_claims_empty_missing_or_duplicate_receipts_verified():
    assert not scope_receipts_valid(None, {("D", "C"): "sha"})
    assert not scope_receipts_valid({}, {})
    duplicate = {"document_id": "D", "chunk_id": "C", "content_sha256": "sha"}
    assert not scope_receipts_valid({"source_units": 2, "exact_full_reads": 2,
        "all_scoped_text_read": True, "read_units": [duplicate, duplicate]},
        {("D", "C"): "sha", ("D", "other"): "sha"})


# Budget-relevant projections of the four original recorded gate failures.
# Full record hashes and the independent accounting are in runtime-budget-audit.json.
RECORDED_TRACES = [
    ("held-028:0:review", 10, [
        (1, "grep"), (2, "read"), (3, "pick"), (4, "grep"), (5, "read"),
        (6, "pick"), (7, "finish"), (7, "review"), (8, "grep"), (9, "read"),
        (10, "pick"), (11, "grep"), (12, "read"),
    ]),
    ("held-028:1:review", 8, [
        (1, "grep"), (2, "read"), (3, "pick"), (4, "finish"), (4, "review"),
        (5, "grep"), (6, "read"), (7, "pick"), (8, "grep"), (9, "read"),
        (10, "pick"),
    ]),
    ("held-028:2:review", 8, [
        (1, "grep"), (2, "read"), (3, "pick"), (4, "finish"), (4, "review"),
        (5, "grep"), (6, "read"), (7, "pick"), (8, "grep"), (9, "read"),
        (10, "pick"),
    ]),
    ("held-050:1:review", 11, [
        (1, "grep"), (2, "grep"), (2, "recall"), (3, "grep"), (3, "grep"),
        (4, "grep"), (4, "recall"), (5, "read"), (6, "pick"), (7, "finish"),
        (7, "review"), (8, "grep"), (9, "grep"), (9, "recall"), (10, "grep"),
        (10, "recall"), (11, "grep"), (11, "recall"),
    ]),
]


def _recorded_episode(case):
    _identity, bound, trace = case
    steps = []
    for round_index, name in trace:
        step = {"round_index": round_index,
                "tool_name": "evidence_review" if name == "review" else (
                    "finish" if name == "finish" else f"corpus.{name}"),
                "observation_text": ""}
        if name == "review":
            step["observation_text"] = json.dumps({
                "status": "insufficient", "attempts": 1, "repairs": 1,
            })
        steps.append(step)
    return {"initial_max_steps": 15, "initial_wall_clock_seconds": 180.0,
            "final_max_steps": bound, "steps_used": bound, "steps": steps}


@pytest.mark.parametrize("case", RECORDED_TRACES, ids=[case[0] for case in RECORDED_TRACES])
def test_recorded_corrections_preserve_the_production_budget(case):
    episode = _recorded_episode(case)
    review = {"status": "unverified", "attempts": 1, "repairs": 1}
    before = copy.deepcopy((episode, review))
    assert production_budget_within_bounds(episode, review, review_enabled=True)
    assert (episode, review) == before


@pytest.mark.parametrize("field,value", [
    ("initial_max_steps", 16), ("initial_max_steps", 14),
    ("initial_wall_clock_seconds", 181), ("initial_wall_clock_seconds", 179),
    ("final_max_steps", 16), ("final_max_steps", 9), ("final_max_steps", 7),
    ("steps_used", 9), ("steps_used", -1), ("steps_used", True),
    ("steps", []),
])
def test_wrong_limits_or_unaccounted_tightening_are_rejected(field, value):
    episode = _recorded_episode(RECORDED_TRACES[1])
    episode[field] = value
    assert not production_budget_within_bounds(
        episode, {"attempts": 1, "repairs": 1}, review_enabled=True,
    )


@pytest.mark.parametrize("repairs", [0, 2, True])
def test_tightening_requires_exactly_one_correction(repairs):
    assert not production_budget_within_bounds(
        _recorded_episode(RECORDED_TRACES[1]),
        {"attempts": 1, "repairs": repairs}, review_enabled=True,
    )


@pytest.mark.parametrize("assessment", [
    "not json", "[]",
    json.dumps({"status": "sufficient", "attempts": 1, "repairs": 1}),
    json.dumps({"status": "insufficient", "attempts": 2, "repairs": 1}),
])
def test_correction_boundary_requires_a_valid_observed_decision(assessment):
    episode = _recorded_episode(RECORDED_TRACES[1])
    next(step for step in episode["steps"] if step["tool_name"] == "evidence_review")[
        "observation_text"
    ] = assessment
    assert not production_budget_within_bounds(
        episode, {"attempts": 1, "repairs": 1}, review_enabled=True,
    )


@pytest.mark.parametrize("enabled,used,expected", [
    (False, 15, True), (False, 16, True), (False, 17, False),
    (True, 15, True), (True, 16, False),
])
def test_baseline_forced_finish_does_not_expand_review_step_limit(enabled, used, expected):
    episode = {"initial_max_steps": 15, "initial_wall_clock_seconds": 180,
               "final_max_steps": 15, "steps_used": used}
    assert production_budget_within_bounds(episode, {}, review_enabled=enabled) is expected


def test_baseline_cannot_tighten_its_limit():
    episode = _recorded_episode(RECORDED_TRACES[1])
    assert not production_budget_within_bounds(episode, {}, review_enabled=False)


@pytest.mark.parametrize("boundary,attempts,bound", [(1, 0, 5), (12, 1, 15)])
def test_empty_evidence_and_late_corrections_use_the_same_shared_budget(boundary, attempts, bound):
    steps = [{"round_index": index + 1, "tool_name": "corpus.grep"}
             for index in range(boundary - attempts)]
    steps[-1]["tool_name"] = "finish"
    steps.append({"round_index": boundary - attempts, "tool_name": "evidence_review",
                  "observation_text": json.dumps({
                      "status": "insufficient", "attempts": attempts, "repairs": 1,
                      "reason": "No final-visible evidence was selected.", "coverage": [],
                  })})
    episode = {"initial_max_steps": 15, "initial_wall_clock_seconds": 180,
               "final_max_steps": bound, "steps_used": boundary, "steps": steps}
    assert production_budget_within_bounds(
        episode, {"attempts": attempts, "repairs": 1}, review_enabled=True,
    )


@pytest.mark.parametrize("reason,coverage", [
    ("A model reported missing evidence.", []),
    ("No final-visible evidence was selected.", [{"facet_id": "F1"}]),
])
def test_invented_zero_call_correction_boundaries_are_rejected(reason, coverage):
    episode = _recorded_episode(RECORDED_TRACES[1])
    episode.update(final_max_steps=7, steps_used=7)
    next(step for step in episode["steps"] if step["tool_name"] == "evidence_review")[
        "observation_text"
    ] = json.dumps({"status": "insufficient", "attempts": 0, "repairs": 1,
                    "reason": reason, "coverage": coverage})
    assert not production_budget_within_bounds(
        episode, {"attempts": 0, "repairs": 1}, review_enabled=True,
    )


def test_real_empty_snapshot_correction_needs_no_model_request(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "packages/shared-python"))
    for key, value in {
        "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
        "TMP_PATH": str(tmp_path), "S3_TEMP_PATH": str(tmp_path),
        "S3_BUCKET_NAME": "test", "S3_ACCESS_KEY_ID": "test",
        "S3_SECRET_ACCESS_KEY": "test", "DS_KEY": "",
    }.items():
        monkeypatch.setenv(key, value)
    from shared.services.retrieval.agent_explore.budget import EpisodeBudget
    from shared.services.retrieval.agent_explore.evidence_review import (
        EvidenceReviewSession,
        EvidenceSnapshot,
    )

    async def load_snapshot(**_kwargs):
        return EvidenceSnapshot(items=(), fingerprint="empty-snapshot")

    async def unexpected_reviewer(_messages, _max_tokens):
        pytest.fail("Empty evidence must not invoke the model")

    budget = EpisodeBudget()
    budget.record_step()  # The explorer's finish already consumed one step.
    session = EvidenceReviewSession("Find evidence", load_snapshot, unexpected_reviewer)
    decision = asyncio.run(session.on_finish(pool=[], queried_tables={}, budget=budget))
    assert decision.continue_retrieval
    assert session.report["attempts"] == 0
    assert session.report["repairs"] == 1
    assert budget.max_steps == 5
    episode = {"initial_max_steps": 15, "initial_wall_clock_seconds": 180,
               "final_max_steps": budget.max_steps, "steps_used": budget.steps_used,
               "steps": [{"tool_name": "finish", "round_index": 1},
                         {"tool_name": "evidence_review", "round_index": 1,
                          "observation_text": json.dumps(session.report)}]}
    assert production_budget_within_bounds(episode, session.report, review_enabled=True)
