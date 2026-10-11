"""New inventory/summarizer and independent scorer regressions; no network calls."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/evidence_review_benchmark"))

from build_rfc_inventory import SOURCE_HASHES, inventory_questions  # noqa: E402
from corpus import prepare_corpus  # noqa: E402
from runtime import digest  # noqa: E402
from score import (SOURCE_SPAN_PROMPT, negative_control_passed, resolve_source_spans,  # noqa: E402
                   semantic_assess, semantic_negative_control, source_spans,
                   validate_semantic_assessment)
from summarize import PRICING_VERSIONS, provider_metrics, validate_schedule  # noqa: E402


def frozen_example():
    gold = {"questions": [{"id": identity, "split": split, "cluster_id": family + "/case"}
                          for identity, split, family in (("dev", "development", "bcp14"),
                                                         ("json-1", "held_out", "json"),
                                                         ("quic-1", "held_out", "quic"))]}
    protocol = {"schedule": [{"question_id": q["id"], "split": q["split"], "repeat": repeat,
                              "order": ["baseline", "review"]}
                             for q in gold["questions"] for repeat in range(2)]}
    trials = [{"id": f"{pair['question_id']}:{pair['repeat']}:{arm}",
               "question_id": pair["question_id"], "split": pair["split"], "repeat": pair["repeat"],
               "arm": arm, "protocol_digest": digest(protocol)}
              for pair in protocol["schedule"] for arm in pair["order"]]
    return gold, protocol, trials


def test_new_families_and_two_repeats_use_frozen_schedule():
    gold, protocol, trials = frozen_example()
    questions, selected, excluded = validate_schedule(trials, gold, protocol=protocol)
    assert set(questions) == {"json-1", "quic-1"}
    assert len(selected) == 8 and len(excluded) == 4
    assert len(validate_schedule(trials, gold, protocol=protocol, split="development")[1]) == 4


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "extra", "digest", "arm", "split", "bool-repeat"])
def test_frozen_schedule_rejects_incomplete_or_mixed_records(mutation):
    gold, protocol, trials = frozen_example()
    if mutation == "missing":
        trials.pop()
    elif mutation == "duplicate":
        trials.append(copy.deepcopy(trials[-1]))
    elif mutation == "extra":
        trials.append({**trials[-1], "id": "quic-1:2:review", "repeat": 2})
    else:
        trial = trials[-1]
        trial[{"digest": "protocol_digest", "arm": "arm", "split": "split", "bool-repeat": "repeat"}[mutation]] = {
            "digest": "other", "arm": "unknown", "split": "development", "bool-repeat": True}[mutation]
    with pytest.raises(ValueError):
        validate_schedule(trials, gold, protocol=protocol)


@pytest.mark.parametrize("mutation", ["missing-question", "repeat-gap", "duplicate-pair", "bad-order"])
def test_frozen_schedule_rejects_malformed_inventory(mutation):
    gold, protocol, trials = frozen_example()
    if mutation == "missing-question":
        protocol["schedule"] = [pair for pair in protocol["schedule"] if pair["question_id"] != "json-1"]
    elif mutation == "repeat-gap":
        protocol["schedule"][-1]["repeat"] = 3
    elif mutation == "duplicate-pair":
        protocol["schedule"].append(copy.deepcopy(protocol["schedule"][-1]))
    else:
        protocol["schedule"][-1]["order"] = ["baseline", "baseline"]
    with pytest.raises(ValueError):
        validate_schedule(trials, gold, protocol=protocol)


def test_complete_sources_and_gold_are_exact_and_unselected(tmp_path):
    path = ROOT / "scripts/fixtures/evidence_review_rfc_20261011/gold.json"
    gold = json.loads(path.read_text())
    assert gold["questions"] == inventory_questions()
    manifest = prepare_corpus(ROOT, path)
    assert len(manifest["documents"]) == 5
    for spec, expected in SOURCE_HASHES.items():
        raw = path.parent / spec / f"{spec}.txt"
        assert hashlib.sha256(raw.read_bytes()).hexdigest() == expected
        originals = json.loads((path.parent / spec / "chunks.json").read_text())["chunks"]
        assert originals[0]["content"] == raw.read_text()
        doc = next(doc for doc in manifest["documents"] if doc["doc_key"] == spec)
        original = originals[0]["content"]
        covered = [False] * len(original)
        for chunk in doc["chunks"]:
            start, end = (chunk["metadata"][key] for key in ("source_start", "source_end"))
            assert chunk["content"] == original[start:end]
            covered[start:end] = [True] * (end - start)
        assert all(covered)
    modified = copy.deepcopy(gold)
    modified["questions"] = []
    changed_gold = tmp_path / "without-labels.json"
    changed_gold.write_text(json.dumps(modified))
    assert prepare_corpus(ROOT, changed_gold) == manifest
    assert len(gold["questions"]) == 30
    for question in gold["questions"]:
        for req in question["requirements"]:
            for proof in req["proofs"]:
                raw = (path.parent / proof["doc_key"] / (proof["doc_key"] + ".txt")).read_text()
                assert all(quote in raw for quote in proof["quotes"])


@pytest.mark.parametrize("text", ["", "a\n\n b\r\n", "表格🙂\n重复\n重复\n", "x" * 513 + "\nend"])
def test_independent_scorer_spans_are_lossless(text):
    spans = source_spans(text)
    assert "".join(span["text"] for span in spans) == text
    assert len({span["span_id"] for span in spans}) == len(spans)
    assert all(len(span["text"]) <= 256 for span in spans)


def span_judgment(citation):
    return {"requirements": [{"id": "r", "status": "supported", "reason": "Exact source range.", "citations": [citation]}]}


@pytest.mark.parametrize("citation", [
    {"evidence_id": "B", "first_span": "L0002", "last_span": "L0001"},
    {"evidence_id": "B", "first_span": "L0000", "last_span": "L0001"},
    {"evidence_id": "wrong", "first_span": "L0001", "last_span": "L0001"},
    {"evidence_id": "B", "first_span": 1, "last_span": "L0001"},
    {"evidence_id": "B", "first_span": "L0001", "last_span": "L9999"},
    {"evidence_id": "B", "quote": "changed or deleted columns"},
])
def test_span_scorer_rejects_forged_or_ambiguous_locators(citation):
    with pytest.raises(ValueError):
        resolve_source_spans(span_judgment(citation), [{"evidence_id": "B", "text": "same\nsame\n"}])


def test_span_scorer_keeps_intervening_table_columns_and_units():
    text = "| period | USD | hours |\n| 2025 | 10 | 20 |\n"
    item = {"evidence_id": "B", "text": text, "document_id": "d", "chunk_id": "c", "revision": "v"}
    result = resolve_source_spans(span_judgment({"evidence_id": "B", "first_span": "L0001", "last_span": "L0002"}), [item])
    quote = result["requirements"][0]["citations"][0]["quote"]
    assert quote == text
    result["requirements"][0]["citations"][0]["quote"] = "| period | hours |\n| 2025 | 20 |"
    assert validate_semantic_assessment(result, [{"id": "r", "text": "Return all table fields.", "proofs": []}], [item])["reason_code"] == "non_exact_evidence_quote"


@pytest.mark.asyncio
async def test_span_semantic_assessment_blind_negative_control_preserves_schema():
    control = semantic_negative_control()
    final_span = source_spans(control["evidence_items"][0]["text"])[-1]["span_id"]
    result = {"requirements": [{"id": identity, "status": status, "reason": "Only the supplied source counts.",
                                "citations": [{"evidence_id": "Bnegativecontrol", "first_span": "L0001", "last_span": final_span}]}
                               for identity, status in control["expected_statuses"].items()]}
    response = SimpleNamespace(model="deepseek-flash", usage=None, choices=[SimpleNamespace(
        finish_reason="stop", message=SimpleNamespace(content=json.dumps(result)))])
    create = AsyncMock(return_value=response)
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    assessed = await semantic_assess(control["query"], control["gold_requirements"], control["evidence_items"], client,
                                     citation_mode="source-spans")
    assert negative_control_passed(assessed)
    sent = create.call_args.kwargs["messages"]
    assert sent[0]["content"] == SOURCE_SPAN_PROMPT
    assert '"first_span"' in SOURCE_SPAN_PROMPT and '"quote"' not in SOURCE_SPAN_PROMPT
    evidence = json.loads(sent[-1]["content"])["evidence_items"][0]
    assert "text" not in evidence
    assert "".join(span["text"] for span in evidence["source_spans"]) == control["evidence_items"][0]["text"]
    assert "arm" not in json.loads(sent[-1]["content"])


def test_versioned_pricing_never_implicitly_relabels_other_dates():
    usage = {"prompt_tokens": 300, "completion_tokens": 20, "total_tokens": 320,
             "prompt_cache_hit_tokens": 100, "prompt_cache_miss_tokens": 200}
    record = {"provider_calls": [{"returned_model": "deepseek-flash", "requested_model": "deepseek-flash",
                                  "usage": usage, "started_at": "2026-10-11T01:00:00Z"}],
              "provider_usage": {"usage_complete": True}}
    assert provider_metrics([record])["list_rate_estimate_usd"] is None
    assert provider_metrics([record], PRICING_VERSIONS["2026-10-11"])["list_rate_estimate_usd"] == pytest.approx(0.0000423)
    record["provider_calls"][0]["started_at"] = "2026-10-12T01:00:00Z"
    assert provider_metrics([record], PRICING_VERSIONS["2026-10-11"])["list_rate_estimate_usd"] is None
