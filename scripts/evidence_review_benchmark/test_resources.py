"""Resource interventions must be explicit, unbounded locally and reversible."""
import math
import os

import pytest

from runtime import prepare_environment
from resources import PROVIDER_MAX_TOKENS, install, request_options, resource_spec
from resources import _apply_options

os.environ.setdefault("DS_KEY", "offline-resource-test")
prepare_environment()

@pytest.mark.parametrize("profile,thinking,effort", [
    ("provider-max-thinking", "enabled", "max"),
    ("provider-max-nonthinking", "disabled", None),
])
def test_official_maximum_without_model_wait_or_local_resource_caps(profile, thinking, effort):
    spec = resource_spec(profile)
    assert all(spec[key] is None for key in (
        "episode_steps", "episode_seconds", "outer_seconds", "review_seconds", "correction_steps", "monetary_budget"))
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
    with install("provider-max-thinking"):
        episode = budget.EpisodeBudget(steps_used=1000)
        assert episode.exhausted() is None
        assert math.isinf(episode.remaining_seconds())
        assert math.isinf(evidence_review.MAX_REVIEW_SECONDS)
        assert evidence_review.MAX_CORRECTION_STEPS > 1000
        assert "1024 tokens" not in evidence_review._SYSTEM_PROMPT
        assert evidence_review.MAX_REVIEW_CALLS == 2
        assert openai_harness.ToolBudget().max_chars > 1000000
        assert openai_harness.AGENT_EXPLORE_MAX_COMPLETION_TOKENS == PROVIDER_MAX_TOKENS
    assert budget.EpisodeBudget is original
    assert budget.EpisodeBudget().max_steps == 15
    assert evidence_review.MAX_REVIEW_SECONDS == 30
    assert evidence_review.MAX_CORRECTION_STEPS == 4
    assert evidence_review._SYSTEM_PROMPT == prompt
    assert openai_harness.AGENT_EXPLORE_MAX_COMPLETION_TOKENS == 1024


def test_thinking_pick_is_auto_only_with_the_same_sole_tool():
    named = {"type": "function", "function": {"name": "corpus_pick"}}
    options = {"model": "deepseek-flash", "tools": [named], "tool_choice": named}
    assert _apply_options(options, "provider-max-thinking")["tool_choice"] == "auto"
    assert _apply_options(options, "provider-max-nonthinking")["tool_choice"] == named
    assert options["tool_choice"] == named
    with pytest.raises(ValueError):
        _apply_options({**options, "tools": [named, named]}, "provider-max-thinking")
