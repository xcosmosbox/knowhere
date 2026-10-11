"""Resource interventions must be explicit, unbounded locally and reversible."""
import math
import os
import asyncio

import pytest

from runtime import prepare_environment
from resources import ACTIVE_SCOPE, PROVIDER_MAX_TOKENS, ScopeProgress, bind_scope, install, request_options, resource_spec
from resources import _apply_options

os.environ.setdefault("DS_KEY", "offline-resource-test")
prepare_environment()

@pytest.mark.parametrize("profile,thinking,effort", [
    ("provider-max-thinking", "enabled", "max"),
    ("provider-max-nonthinking", "disabled", None),
    ("provider-max-scoped-thinking", "enabled", "max"),
])
def test_official_maximum_without_model_wait_or_local_resource_caps(profile, thinking, effort):
    spec = resource_spec(profile)
    assert all(spec[key] is None for key in (
        "episode_steps", "episode_seconds", "outer_seconds", "review_seconds", "correction_steps", "monetary_budget",
        "review_input_bytes", "review_assessment_bytes", "resolved_citation_bytes"))
    options = request_options(profile)
    assert options["max_tokens"] == PROVIDER_MAX_TOKENS == 393216
    assert options["timeout"] is None
    assert options["extra_body"] == {"thinking": {"type": thinking}}
    assert options.get("reasoning_effort") == effort
    assert ("temperature" not in options) == (thinking == "enabled")


def test_unrestricted_intervention_restores_all_production_defaults():
    from shared.services.retrieval.agent_explore import budget, evidence_review
    from shared.services.retrieval.agent_explore.harness import openai_harness
    original = budget.EpisodeBudget
    prompt = evidence_review._SYSTEM_PROMPT
    byte_limits = (evidence_review.MAX_REVIEW_INPUT_BYTES, evidence_review.MAX_REVIEW_ASSESSMENT_BYTES,
                   evidence_review.MAX_REVIEW_CITATION_BYTES)
    with install("provider-max-thinking"):
        episode = budget.EpisodeBudget(steps_used=1000)
        assert episode.exhausted() is None
        assert math.isinf(episode.remaining_seconds())
        assert math.isinf(evidence_review.MAX_REVIEW_SECONDS)
        assert evidence_review.MAX_CORRECTION_STEPS > 1000
        assert "1024 tokens" not in evidence_review._SYSTEM_PROMPT
        assert "16384 UTF-8 bytes" not in evidence_review._SYSTEM_PROMPT
        assert min(evidence_review.MAX_REVIEW_INPUT_BYTES, evidence_review.MAX_REVIEW_ASSESSMENT_BYTES,
                   evidence_review.MAX_REVIEW_CITATION_BYTES) > 100000000
        assert evidence_review.MAX_REVIEW_CALLS == 2
        assert openai_harness.ToolBudget().max_chars > 1000000
        assert openai_harness.AGENT_EXPLORE_MAX_COMPLETION_TOKENS == PROVIDER_MAX_TOKENS
    assert budget.EpisodeBudget is original
    assert budget.EpisodeBudget().max_steps == 15
    assert evidence_review.MAX_REVIEW_SECONDS == 30
    assert evidence_review.MAX_CORRECTION_STEPS == 4
    assert evidence_review._SYSTEM_PROMPT == prompt
    assert (evidence_review.MAX_REVIEW_INPUT_BYTES, evidence_review.MAX_REVIEW_ASSESSMENT_BYTES,
            evidence_review.MAX_REVIEW_CITATION_BYTES) == byte_limits
    assert openai_harness.AGENT_EXPLORE_MAX_COMPLETION_TOKENS == 1024


def test_thinking_pick_is_auto_only_with_the_same_sole_tool():
    named = {"type": "function", "function": {"name": "corpus_pick"}}
    options = {"model": "deepseek-flash", "tools": [named], "tool_choice": named}
    assert _apply_options(options, "provider-max-thinking")["tool_choice"] == "auto"
    assert _apply_options(options, "provider-max-nonthinking")["tool_choice"] == named
    assert options["tool_choice"] == named
    with pytest.raises(ValueError):
        _apply_options({**options, "tools": [named, named]}, "provider-max-thinking")


def scope_manifest():
    return {"documents": [
        {"document_id": "D1", "source_file_name": "full.txt", "requirements": ["SECRET GOLD"],
         "chunks": [{"chunk_id": "C1", "type": "text", "content": "完整的\nbody one"},
                    {"chunk_id": "C2", "type": "text", "content": "body two"}]},
        {"document_id": "D2", "source_file_name": "outside.txt",
         "chunks": [{"chunk_id": "C3", "type": "text", "content": "outside scope"}]},
    ]}


def full_read(*rows, error=None, text=None):
    from shared.services.retrieval.agent_tools import ToolResult
    return ToolResult(text="\n".join(str(row.get("content", "")) for row in rows) if text is None else text,
                      payload={"chunks": list(rows)}, error=error)


def test_scope_counts_exact_visible_full_reads_not_picks_or_sufficiency():
    with bind_scope(scope_manifest(), ["D1"]) as scope:
        assert scope.report()["source_units"] == 2
        assert scope.report()["exact_full_reads"] == 0
        assert "SECRET GOLD" not in scope.instruction()
        assert "outside.txt" not in scope.instruction()
        assert "body one" not in scope.instruction()
        assert "SOURCE_SCOPE_EXHAUSTED" not in scope.instruction()
        first = {"document_id": "D1", "chunk_id": "C1", "content": "完整的\nbody one"}
        scope.observe_read(full_read(first))
        scope.observe_read(full_read(first))
        assert scope.report()["exact_full_reads"] == 1
        assert "SOURCE_SCOPE_EXHAUSTED" not in scope.instruction()
        scope.observe_read(full_read({"document_id": "D1", "chunk_id": "C2", "content": "body two"}))
        assert scope.report()["all_scoped_text_read"] is True
        assert "After the mandatory pick phase" in scope.instruction()
        assert "even if a requested fact remains missing" in scope.instruction()
        assert "not a claim that every query requirement is satisfied" in scope.instruction()


@pytest.mark.parametrize("row,error,text", [
    ({"document_id": "D1", "chunk_id": "C1", "content": "完整的\nbody"}, None, None),
    ({"document_id": "D1", "chunk_id": "C1", "content": "完整的 body one"}, None, None),
    ({"document_id": "D1", "chunk_id": "C1", "content": "完整的\nbody one"}, "failed", None),
    ({"document_id": "D1", "chunk_id": "C1", "content": "完整的\nbody one"}, None, "truncated"),
    ({"document_id": "D2", "chunk_id": "C3", "content": "outside scope"}, None, None),
    ({"document_id": "D1", "chunk_id": "invented", "content": "完整的\nbody one"}, None, None),
    ({"document_id": [], "chunk_id": "C1", "content": "完整的\nbody one"}, None, None),
])
def test_wrong_source_truncated_mutated_failed_or_invisible_reads_never_exhaust_scope(row, error, text):
    with bind_scope(scope_manifest(), ["D1"]) as scope:
        scope.observe_read(full_read(row, error=error, text=text))
        assert scope.report()["exact_full_reads"] == 0
        assert scope.report()["all_scoped_text_read"] is False


@pytest.mark.parametrize("document_ids", [[], ["D1", "D1"], ["missing"], ["D1", "missing"]])
def test_scope_must_be_an_exact_nonempty_unique_frozen_subset(document_ids):
    with pytest.raises(ValueError), bind_scope(scope_manifest(), document_ids):
        pass
    assert ACTIVE_SCOPE.get() is None


def test_scope_context_is_restored_on_nested_failure_and_isolated_between_tasks():
    assert ACTIVE_SCOPE.get() is None
    with bind_scope(scope_manifest(), ["D1"]) as outer:
        with pytest.raises(RuntimeError), bind_scope(scope_manifest(), ["D2"]) as inner:
            assert ACTIVE_SCOPE.get() is inner
            raise RuntimeError("fixture exception")
        assert ACTIVE_SCOPE.get() is outer
    assert ACTIVE_SCOPE.get() is None

    async def one(doc):
        with bind_scope(scope_manifest(), [doc]) as scope:
            await asyncio.sleep(0)
            assert ACTIVE_SCOPE.get() is scope
            assert await asyncio.to_thread(lambda: ACTIVE_SCOPE.get() is scope)
            return scope.documents[0]["document_id"]
    async def concurrent():
        return await asyncio.gather(one("D1"), one("D2"))
    assert asyncio.run(concurrent()) == ["D1", "D2"]
    assert ACTIVE_SCOPE.get() is None


def test_scope_feedback_is_opt_in_and_never_substitutes_tool_results(monkeypatch):
    from shared.services.retrieval.agent_explore import budget
    from shared.services.retrieval.agent_explore.evidence_pool import EvidencePool
    from shared.services.retrieval.agent_explore.harness import openai_harness as harness
    result = full_read({"document_id": "D1", "chunk_id": "C1", "content": "完整的\nbody one"})
    calls = []
    async def dispatch(name, args, **kwargs):
        calls.append((name, args, kwargs))
        return result
    monkeypatch.setattr(harness, "dispatch_tool_call", dispatch)
    original_compose = harness._compose_user_content
    with install("provider-max-scoped-thinking"):
        with pytest.raises(ValueError):
            harness._compose_user_content()
        with bind_scope(scope_manifest(), ["D1"]) as scope:
            assert asyncio.run(harness.dispatch_tool_call("corpus.grep", {"pattern": "body"})) is result
            assert scope.report()["exact_full_reads"] == 0
            args = {"refs": [{"document_id": "D1", "chunk_id": "C1"}]}
            assert asyncio.run(harness.dispatch_tool_call("corpus.read", args, query="test")) is result
            assert calls[-1] == ("corpus.read", args, {"query": "test"})
            assert scope.report()["exact_full_reads"] == 1
            rendered = harness._compose_user_content(query="original query", trace_lines=[], latest_results=[],
                latest_turn=1, pool=EvidencePool(), budget=budget.EpisodeBudget(), instruction=harness._PICK_PHASE_INSTRUCTION)
            assert "User query: original query" in rendered
            assert harness._PICK_PHASE_INSTRUCTION in rendered
            assert "Experimental closed source scope" in rendered
            assert "SECRET GOLD" not in rendered
    assert harness.dispatch_tool_call is dispatch
    assert harness._compose_user_content is original_compose
    with install("provider-max-thinking"):
        assert harness.dispatch_tool_call is dispatch
        assert harness._compose_user_content is original_compose


def test_empty_scope_is_not_claimed_exhausted():
    assert ScopeProgress([], {}).report()["all_scoped_text_read"] is False
