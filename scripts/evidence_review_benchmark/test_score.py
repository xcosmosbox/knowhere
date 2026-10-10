"""Scorer contract/adversarial tests; no credentials, model calls or database."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages/shared-python"))
sys.path.insert(0, str(ROOT))

from scripts.evidence_review_benchmark.score import (  # noqa: E402
    SYSTEM_PROMPT,
    build_blinded_packet,
    build_snapshot_packet,
    negative_control_passed,
    semantic_assess,
    semantic_negative_control,
    span_assess,
    validate_semantic_assessment,
)


@pytest.fixture
def example():
    text = "Launch approved by Operations.\nLogs retained for 30 days.\n[images/chart.png]"
    metadata = {"original_chunk_id": "original-page", "source_start": 0,
                "source_end": len(text), "source_sha256": "source-sha"}
    manifest = {"documents": [{
        "doc_key": "source", "document_id": "doc-1", "job_result_id": "revision-1",
        "source_file_name": "file.txt", "source_sha256": "source-sha",
        "chunks": [{"chunk_id": "derived-1", "type": "text", "content": text,
                    "path": "file.txt/Approvals/Launch", "metadata": metadata}],
    }], "revision_pins": {"doc-1": "revision-1"}}
    row = {"chunk_id": "derived-1", "chunk_type": "text", "content": text,
           "job_result_id": "revision-1", "metadata": dict(metadata),
           "source": {"document_id": "doc-1", "job_result_id": "revision-1",
                      "source_file_name": "file.txt", "section_path": "Approvals / Launch"}}
    trial = {"id": "secret-episode-id", "arm": "review", "revision_pins": {"doc-1": "revision-1"},
             "response": {"results": [row], "evidence": [
                 {"type": "text", "text": "[E1] [§ file.txt / Approvals]"},
                 {"type": "text", "text": "  Launch approved by Operations.\n  Logs retained for 30 days.\n"},
             ], "evidence_review": {"status": "sufficient"},
                 "decision_trace": [{"private_arm_marker": "must-not-be-read"}]}}
    gold = {"query": "Who approved launch and how long are logs retained?", "doc_keys": ["source"],
            "gold_notes": "Only source body text counts.", "requirements": [
                {"id": "r1", "text": "Identify Operations as approver.",
                 "proofs": [{"doc_key": "source", "chunk_id": "original-page",
                             "quotes": ["Launch approved by Operations."]}]},
                {"id": "r2", "text": "Identify 30-day log retention.",
                 "proofs": [{"doc_key": "source", "chunk_id": "original-page",
                             "quotes": ["Logs retained for 30 days."]}]},
            ]}
    return trial, gold, manifest


def test_blinding_and_exact_provenance_visible_mapping(example):
    trial, gold, manifest = example
    packet = build_blinded_packet(trial, gold, manifest)
    altered = copy.deepcopy(trial)
    altered.update(arm="baseline", id="other-id")
    altered["response"]["evidence_review"] = {"status": "unverified"}
    altered["response"]["decision_trace"] = [{"whatever": "irrelevant"}]
    assert build_blinded_packet(altered, gold, manifest) == packet
    assert len(packet["evidence_items"]) == 1
    item = packet["evidence_items"][0]
    assert item["original_chunk_id"] == "original-page"
    assert item["revision"] == "revision-1"
    assert item["text"] == "Launch approved by Operations.\nLogs retained for 30 days.\n"
    assert item["visible_part_index"] == 1
    assert packet["limitations"] == []
    score = span_assess(packet)
    assert score["coverage"] == 1
    assert score["semantic_sufficiency"] is None


def test_chunk_id_without_final_visible_proof_is_not_coverage(example):
    trial, gold, manifest = example
    trial["response"]["evidence"] = [{"type": "text", "text": "A related launch outline."}]
    packet = build_blinded_packet(trial, gold, manifest)
    assert packet["evidence_items"] == []
    assert span_assess(packet)["coverage"] == 0
    assert packet["limitations"] == [{"code": "row_not_located_in_final_evidence", "row_index": 0}]


def test_visible_truncation_never_filled_from_manifest(example):
    trial, gold, manifest = example
    trial["response"]["evidence"][1]["text"] = "  Launch approved by Operations."
    packet = build_blinded_packet(trial, gold, manifest)
    assert not packet["evidence_items"]
    assert not span_assess(packet)["all_gold_quotes_covered"]


@pytest.mark.parametrize("mutator,reason", [
    (lambda row: row.update(content="Fabricated text"), "content_does_not_match_frozen_chunk"),
    (lambda row: row.update(job_result_id="wrong"), "missing_or_mismatched_revision"),
    (lambda row: row["metadata"].update(original_chunk_id="wrong"), "row_provenance_disagrees_with_manifest"),
    (lambda row: row["source"].update(document_id="wrong"), "unknown_document_or_chunk"),
    (lambda row: row["source"].update(source_file_name="other"), "source_name_disagrees_with_manifest"),
    (lambda row: row["source"].update(section_path="other"), "section_path_disagrees_with_manifest"),
])
def test_invalid_source_identity_is_excluded(example, mutator, reason):
    trial, gold, manifest = example
    mutator(trial["response"]["results"][0])
    packet = build_blinded_packet(trial, gold, manifest)
    assert packet["evidence_items"] == []
    assert reason in [limitation["code"] for limitation in packet["limitations"]]


def test_trial_pins_work_without_public_revision_but_must_agree(example):
    trial, gold, manifest = example
    row = trial["response"]["results"][0]
    row.pop("job_result_id")
    row["source"].pop("job_result_id")
    assert build_blinded_packet(trial, gold, manifest)["evidence_items"]
    trial["revision_pins"]["doc-1"] = "wrong"
    assert not build_blinded_packet(trial, gold, manifest)["evidence_items"]
    trial.pop("revision_pins")
    assert not build_blinded_packet(trial, gold, manifest)["evidence_items"]


def test_same_literal_quote_under_wrong_original_owner_does_not_count(example):
    trial, gold, manifest = example
    gold["requirements"][0]["proofs"][0]["chunk_id"] = "another-source-page"
    packet = build_blinded_packet(trial, gold, manifest)
    result = span_assess(packet)
    assert result["coverage"] == 0.5
    assert not result["requirements"][0]["covered"]


def test_all_quotes_in_one_proof_required_but_proof_alternatives_allowed(example):
    trial, gold, manifest = example
    proof = gold["requirements"][0]["proofs"][0]
    proof["quotes"].append("A missing mandatory facet.")
    assert span_assess(build_blinded_packet(trial, gold, manifest))["coverage"] == 0.5
    gold["requirements"][0]["proofs"].append({
        "doc_key": "source", "chunk_id": "original-page",
        "quotes": ["Launch approved by Operations."],
    })
    assert span_assess(build_blinded_packet(trial, gold, manifest))["coverage"] == 1


def test_visual_and_outline_text_cannot_be_credited_as_body(example):
    trial, gold, manifest = example
    trial["response"]["evidence"] = [
        {"type": "text", "text": "[E1] [§ file.txt]"},
        trial["response"]["evidence"][1],
        {"type": "image", "data": "not-decoded"},
    ]
    packet = build_blinded_packet(trial, gold, manifest)
    assert not packet["evidence_items"]
    assert "non_text_evidence_not_scored" in [item["code"] for item in packet["limitations"]]


def test_missing_response_is_an_explicit_limitation(example):
    _trial, gold, manifest = example
    packet = build_blinded_packet({"error": "TimeoutError"}, gold, manifest)
    assert packet["limitations"] == [{"code": "missing_response"}]
    assert span_assess(packet)["coverage"] == 0


def _judgments(control, *, forge=False):
    quotes = {
        "negative.production": "The pilot was approved on 14 May 2026.",
        "negative.retention": "Pilot logs are retained for 30 days.",
        "negative.growth": "Pilot throughput was 25 units per hour.",
    }
    return {"requirements": [
        {"id": identity, "status": "supported" if forge else status,
         "reason": "A cited fact is evaluated against the fixed requirement.",
         "citations": [{"evidence_id": "Bnegativecontrol", "quote": quotes[identity]}]}
        for identity, status in control["expected_statuses"].items()
    ]}


def test_explicit_semantic_negative_control_exposes_literal_validation_limit():
    control = semantic_negative_control()
    span = span_assess(control)
    assert span["coverage"] == pytest.approx(1 / 3)
    forged = validate_semantic_assessment(
        _judgments(control, forge=True), control["gold_requirements"], control["evidence_items"],
    )
    # Exact citations pass syntax, but wrong relations must fail the semantic gate.
    assert forged["status"] == "valid"
    assert forged["all_supported"] is True
    assert not negative_control_passed(forged)
    correct = validate_semantic_assessment(
        _judgments(control), control["gold_requirements"], control["evidence_items"],
    )
    assert negative_control_passed(correct)


@pytest.mark.parametrize("mutation,reason", [
    (lambda data: data["requirements"].pop(), "missing_duplicate_or_unknown_requirement"),
    (lambda data: data["requirements"][1].update(id="negative.production"), "missing_duplicate_or_unknown_requirement"),
    (lambda data: data["requirements"][0].update(id="unknown"), "missing_duplicate_or_unknown_requirement"),
    (lambda data: data["requirements"][1].update(status=[]), "invalid_requirement_status"),
    (lambda data: data["requirements"][1].update(citations=[]), "assertion_without_citation"),
    (lambda data: data["requirements"][1]["citations"][0].update(quote="Logs retained forever."), "non_exact_evidence_quote"),
    (lambda data: data["requirements"][1]["citations"][0].update(quote="   "), "empty_evidence_quote"),
    (lambda data: data["requirements"][1]["citations"][0].update(evidence_id="invented"), "unknown_evidence_id"),
])
def test_semantic_invalid_facets_and_citations_have_unknown_scores(mutation, reason):
    control = semantic_negative_control()
    data = _judgments(control)
    mutation(data)
    result = validate_semantic_assessment(data, control["gold_requirements"], control["evidence_items"])
    assert result["status"] == "invalid"
    assert result["reason_code"] == reason
    assert result["semantic_coverage"] is None
    assert result["all_supported"] is None


def _client(content, *, finish_reason="stop", model="deepseek-flash"):
    response = SimpleNamespace(
        model=model, usage={"prompt_tokens": 80, "completion_tokens": 60, "total_tokens": 140},
        choices=[SimpleNamespace(finish_reason=finish_reason,
                                 message=SimpleNamespace(content=content))],
    )
    create = AsyncMock(return_value=response)
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


@pytest.mark.asyncio
async def test_async_judge_uses_blind_payload_exact_model_and_fixed_parameters():
    control = semantic_negative_control()
    items = copy.deepcopy(control["evidence_items"])
    items[0].update(arm="review", evidence_review={"status": "sufficient"}, trace="secret")
    client = _client(json.dumps(_judgments(control)))
    result = await semantic_assess(control["query"], control["gold_requirements"], items, client)
    assert negative_control_passed(result)
    kwargs = client.chat.completions.create.await_args.kwargs
    assert kwargs["model"] == "deepseek-flash"
    assert kwargs["temperature"] == 0
    assert kwargs["max_tokens"] == 2048
    assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
    assert kwargs["response_format"] == {"type": "json_object"}
    assert kwargs["messages"][0]["content"] == SYSTEM_PROMPT
    payload = json.loads(kwargs["messages"][1]["content"])
    assert set(payload) == {"query", "gold_requirements", "evidence_items"}
    assert not {"arm", "evidence_review", "trace"} & payload["evidence_items"][0].keys()
    assert result["usage"]["total_tokens"] == 140


@pytest.mark.asyncio
@pytest.mark.parametrize("content,finish_reason,model", [
    ("not json", "stop", "deepseek-flash"),
    ('{"requirements": [], "requirements": []}', "stop", "deepseek-flash"),
    ("{}", "length", "deepseek-flash"),
    ("{}", "stop", "other-model"),
])
async def test_malformed_or_truncated_judge_response_is_unknown(content, finish_reason, model):
    control = semantic_negative_control()
    result = await semantic_assess(
        control["query"], control["gold_requirements"], control["evidence_items"],
        _client(content, finish_reason=finish_reason, model=model),
    )
    assert result["status"] == "error"
    assert result["semantic_coverage"] is None
    assert result["all_supported"] is None
    assert result["usage"]["total_tokens"] == 140


@pytest.mark.asyncio
async def test_provider_failure_does_not_record_exception_body_or_invent_usage():
    control = semantic_negative_control()
    client = _client("unused")
    client.chat.completions.create.side_effect = RuntimeError("sensitive transport detail")
    result = await semantic_assess(control["query"], control["gold_requirements"], control["evidence_items"], client)
    assert result["status"] == "error"
    assert result["error_type"] == "RuntimeError"
    assert result["usage"] is None
    assert "sensitive" not in json.dumps(result)


@pytest.mark.parametrize("mutation,reason", [
    (lambda items: items[0].pop("revision"), "unverifiable_evidence_source"),
    (lambda items: items[0].update(document_id=""), "unverifiable_evidence_source"),
    (lambda items: items.append(copy.deepcopy(items[0])), "duplicate_evidence_id"),
])
def test_semantic_quotes_require_unambiguous_source_revision_identity(mutation, reason):
    control = semantic_negative_control()
    mutation(control["evidence_items"])
    result = validate_semantic_assessment(_judgments(control), control["gold_requirements"], control["evidence_items"])
    assert result["status"] == "invalid"
    assert result["reason_code"] == reason
    assert result["semantic_coverage"] is None



def _snapshot_from_packet(packet):
    return {"items": [{key: item[key] for key in (
        "evidence_id", "document_id", "chunk_id", "section_path", "source_file_name", "text", "revision",
    )} for item in packet["evidence_items"]], "fingerprint": "recorded-fingerprint", "limitation": None}


def test_snapshot_uses_same_blind_identity_and_gold_mapping_as_final(example):
    trial, gold, manifest = example
    final = build_blinded_packet(trial, gold, manifest)
    snapshot = _snapshot_from_packet(final)
    snapshot["items"][0]["evidence_id"] = "Cproduction-reviewer-identity"
    first = build_snapshot_packet(snapshot, gold, manifest)
    assert first["evidence_items"][0]["evidence_id"] == final["evidence_items"][0]["evidence_id"]
    assert first["evidence_items"][0]["text"] == final["evidence_items"][0]["text"]
    assert first["limitations"] == []
    assert span_assess(first)["coverage"] == 1


@pytest.mark.parametrize("mutation,reason", [
    (lambda item: item.update(text="Launch approved by Operations."), "snapshot_text_does_not_match_frozen_chunk"),
    (lambda item: item.update(revision="wrong"), "missing_or_mismatched_revision"),
    (lambda item: item.update(chunk_id="wrong"), "unknown_document_or_chunk"),
    (lambda item: item.update(section_path="wrong"), "section_path_disagrees_with_manifest"),
])
def test_snapshot_never_repairs_missing_or_mismatched_evidence(example, mutation, reason):
    trial, gold, manifest = example
    snapshot = _snapshot_from_packet(build_blinded_packet(trial, gold, manifest))
    mutation(snapshot["items"][0])
    packet = build_snapshot_packet(snapshot, gold, manifest)
    assert not packet["evidence_items"]
    assert packet["limitations"] == [{"code": reason, "item_index": 0}]


def test_snapshot_limitation_preserved_and_no_hidden_manifest_content_added(example):
    _trial, gold, manifest = example
    packet = build_snapshot_packet({"items": [], "fingerprint": "ignored", "limitation": "visual_evidence_not_reviewed"}, gold, manifest)
    assert packet["evidence_items"] == []
    assert packet["limitations"] == [{"code": "snapshot_limitation", "detail": "visual_evidence_not_reviewed"}]
