"""Strict, descriptive summary of the frozen 300-episode held-out experiment.

Repetitions are averaged within each question before paired differences are
aggregated. The two document families are not treated as 150 independent pairs;
no p-values, bootstrap confidence intervals or population significance are given.
Unknown semantic assessments remain unknown. Recorded delivery errors are known
failures to deliver a sufficient result, not claims of semantic insufficiency.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "scripts/fixtures/evidence_review_live_gold.json"
ARMS = ("baseline", "review")
TOKEN_FIELDS = ("prompt_tokens", "completion_tokens", "total_tokens",
                "prompt_cache_hit_tokens", "prompt_cache_miss_tokens")
PRICING = {
    "model": "deepseek-flash", "currency": "USD", "valid_utc_date": "2026-10-10",
    "schedule": "Saturday, all-day off-peak",
    "usd_per_million_tokens": {"prompt_cache_hit_tokens": 0.003,
                               "prompt_cache_miss_tokens": 0.15,
                               "completion_tokens": 0.6},
    "interpretation": "Official daily list-rate estimate, not an invoice; all other dates are unknown.",
}


def read_lines(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ValueError(f"Missing required input: {path}")
    records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if any(not isinstance(record, dict) for record in records):
        raise ValueError(f"Expected JSON objects in {path}")
    return records


def unique_index(records: list[dict[str, Any]], key: str, label: str) -> dict[str, dict[str, Any]]:
    result = {}
    for record in records:
        identity = record.get(key)
        if not isinstance(identity, str) or not identity or identity in result:
            raise ValueError(f"Missing or duplicate {label} identity")
        result[identity] = record
    return result


def number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def ratio(numerator: float, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def distribution(values: list[Any]) -> dict[str, Any]:
    known = sorted(float(value) for value in values if number(value))
    def percentile(fraction: float) -> float | None:
        if not known:
            return None
        position = (len(known) - 1) * fraction
        lower = int(position)
        upper = min(lower + 1, len(known) - 1)
        return known[lower] + (known[upper] - known[lower]) * (position - lower)
    return {"observed": len(known), "unknown": len(values) - len(known),
            "mean": mean(known), "p50": percentile(0.5), "p95": percentile(0.95),
            "minimum": min(known) if known else None, "maximum": max(known) if known else None,
            "percentile_method": "linear interpolation of observed episode values"}


def validate_schedule(
    trials: list[dict[str, Any]], gold: dict[str, Any], *, expected_questions: int = 50,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    questions = unique_index(gold["questions"], "id", "gold question")
    held_out = {identity: question for identity, question in questions.items()
                if question["split"] == "held_out"}
    if len(held_out) != expected_questions:
        raise ValueError(f"Expected {expected_questions} held-out questions")
    families = Counter(question["cluster_id"].split("/", 1)[0] for question in held_out.values())
    if set(families) != {"micron", "spacex"}:
        raise ValueError("The frozen held-out benchmark must contain the two specified document families")
    if expected_questions == 50 and families != {"micron": 25, "spacex": 25}:
        raise ValueError("The frozen benchmark must contain 25 questions per held-out family")
    unique_index(trials, "id", "trial")
    selected, excluded = [], []
    for trial in trials:
        question = questions.get(trial.get("question_id"))
        if question is None or trial.get("split") != question["split"]:
            raise ValueError("Trial question/split does not match the frozen gold inventory")
        arm, repeat = trial.get("arm"), trial.get("repeat")
        if arm not in ARMS or type(repeat) is not int or repeat < 0:
            raise ValueError("Invalid trial arm or repeat")
        if trial["id"] != f"{question['id']}:{repeat}:{arm}":
            raise ValueError("Trial id does not match question, repeat and arm")
        (selected if question["split"] == "held_out" else excluded).append(trial)
    expected = {f"{identity}:{repeat}:{arm}" for identity in held_out
                for repeat in range(3) for arm in ARMS}
    actual = {trial["id"] for trial in selected}
    if actual != expected:
        raise ValueError(f"Incomplete or unexpected held-out schedule: missing={len(expected - actual)}, extra={len(actual - expected)}")
    protocols = {trial.get("protocol_digest") for trial in selected}
    if len(protocols) != 1 or not next(iter(protocols)):
        raise ValueError("All held-out trials must share one frozen protocol digest")
    return held_out, selected, excluded


def _complete_usage(call: dict[str, Any]) -> bool:
    usage = call.get("usage")
    return (isinstance(usage, dict)
            and all(type(usage.get(field)) is int and usage[field] >= 0 for field in TOKEN_FIELDS)
            and usage["prompt_tokens"] + usage["completion_tokens"] == usage["total_tokens"]
            and usage["prompt_cache_hit_tokens"] + usage["prompt_cache_miss_tokens"] == usage["prompt_tokens"])


def _call_cost(call: dict[str, Any]) -> float | None:
    if not _complete_usage(call) or call.get("returned_model") != PRICING["model"]:
        return None
    try:
        started = datetime.fromisoformat(call["started_at"].replace("Z", "+00:00"))
        if started.tzinfo is None or started.astimezone(timezone.utc).date().isoformat() != PRICING["valid_utc_date"]:
            return None
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    return sum(call["usage"][field] * rate / 1_000_000
               for field, rate in PRICING["usd_per_million_tokens"].items())


def provider_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Count every captured request, including retries; missing usage is not zero."""
    calls = [call for record in records for call in record.get("provider_calls", [])]
    flags = [record.get("provider_usage", {}).get("usage_complete") is True for record in records]
    totals = {field: sum(call["usage"][field] for call in calls
                         if isinstance(call.get("usage"), dict)
                         and type(call["usage"].get(field)) is int and call["usage"][field] >= 0)
              for field in TOKEN_FIELDS}
    missing = {field: sum(not (isinstance(call.get("usage"), dict)
                              and type(call["usage"].get(field)) is int
                              and call["usage"][field] >= 0) for call in calls)
               for field in TOKEN_FIELDS}
    complete_calls = sum(_complete_usage(call) for call in calls)
    complete = all(flags) and complete_calls == len(calls)
    costs = [_call_cost(call) for call in calls]
    cost_complete = complete and all(cost is not None for cost in costs)
    return {
        "record_count": len(records), "calls": len(calls),
        "calls_by_kind": dict(sorted(Counter(call.get("kind", "unknown") for call in calls).items())),
        "calls_by_status": dict(sorted(Counter(call.get("status", "unknown") for call in calls).items())),
        "http_statuses": dict(sorted(Counter(str(call.get("http_status", "unknown")) for call in calls).items())),
        "requested_models": dict(sorted(Counter(call.get("requested_model") or "unknown" for call in calls).items())),
        "returned_models": dict(sorted(Counter(call.get("returned_model") or "unknown" for call in calls).items())),
        "model_mismatch_calls": sum(call.get("requested_model") != "deepseek-flash"
                                    or call.get("returned_model") not in (None, "deepseek-flash") for call in calls),
        "complete_usage_calls": complete_calls, "incomplete_usage_calls": len(calls) - complete_calls,
        "records_with_unknown_usage": sum(not flag for flag in flags),
        "usage_complete": complete, "observed_tokens": totals,
        "complete_tokens": totals if complete else None, "missing_fields_by_call": missing,
        "known_list_rate_estimate_usd": sum(cost for cost in costs if cost is not None),
        "unknown_cost_calls": sum(cost is None for cost in costs),
        "cost_complete": cost_complete,
        "list_rate_estimate_usd": sum(costs) if cost_complete else None,
        "pricing": PRICING,
    }


def _semantic(assessment: dict[str, Any], packet: dict[str, Any], question: dict[str, Any]) -> dict[str, Any]:
    result = assessment.get("semantic", {})
    unknown = {"sufficient": None, "coverage": None, "status": result.get("status", "missing"),
               "reason": result.get("reason_code") or "unverified_assessment"}
    if packet.get("limitations"):
        return {**unknown, "reason": "evidence_mapping_limitation"}
    if result.get("status") != "valid":
        return unknown
    requirements = result.get("requirements", [])
    expected = {item["id"] for item in question["requirements"]}
    identities = [item.get("id") for item in requirements]
    if len(identities) != len(expected) or set(identities) != expected:
        raise ValueError("Valid semantic assessment does not cover exactly the frozen requirements")
    statuses = [item.get("status") for item in requirements]
    if any(status not in {"supported", "missing", "conflicting"} for status in statuses):
        raise ValueError("Valid semantic assessment has an unknown requirement status")
    coverage = statuses.count("supported") / len(statuses)
    sufficient = all(status == "supported" for status in statuses)
    if result.get("all_supported") is not sufficient or not number(result.get("semantic_coverage")) or abs(result["semantic_coverage"] - coverage) > 1e-12:
        raise ValueError("Semantic totals disagree with requirement judgments")
    return {"sufficient": sufficient, "coverage": coverage, "status": "valid", "reason": None}


def build_observations(
    trials: list[dict[str, Any]], questions: dict[str, dict[str, Any]],
    mappings: dict[str, dict[str, Any]], packets: dict[str, dict[str, Any]],
    assessments: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    from score import span_assess
    observations = []
    for trial in trials:
        question = questions[trial["question_id"]]
        if trial["id"] not in mappings:
            raise ValueError("A scheduled held-out episode has no blinded packet mapping")
        mapping = mappings[trial["id"]]
        final_id = mapping["final_packet"]
        if final_id not in packets or final_id not in assessments:
            raise ValueError("A scheduled held-out episode lacks a packet or completed assessment record")
        final = _semantic(assessments[final_id], packets[final_id], question)
        if mapping.get("delivery_error") != trial.get("error"):
            raise ValueError("Packet mapping delivery error differs from raw trial")
        if packets[final_id]["query"] != question["query"]:
            raise ValueError("Blinded packet query differs from frozen question")
        response = trial.get("response") or {}
        review = response.get("evidence_review") or {}
        first_eligible = trial["arm"] == "review" and review.get("attempts", 0) > 0 and len(trial.get("snapshots", [])) >= 2
        if bool(mapping.get("first_packet")) != first_eligible:
            raise ValueError("First-finish packet does not match recorded snapshot eligibility")
        first = None
        evidence_changed = None
        if first_eligible:
            first_id = mapping["first_packet"]
            if first_id not in packets or first_id not in assessments:
                raise ValueError("An eligible first finish has no packet or completed assessment record")
            if packets[first_id]["query"] != question["query"]:
                raise ValueError("First-finish packet query differs from frozen question")
            first = _semantic(assessments[first_id], packets[first_id], question)
            first_content = sorted((item["evidence_id"], item["text"]) for item in packets[first_id]["evidence_items"])
            final_content = sorted((item["evidence_id"], item["text"]) for item in packets[final_id]["evidence_items"])
            evidence_changed = first_content != final_content
        delivery_error = trial.get("error") is not None
        observations.append({
            "trial_id": trial["id"], "question_id": question["id"], "repeat": trial["repeat"],
            "arm": trial["arm"], "family": question["cluster_id"].split("/", 1)[0],
            "cluster_id": question["cluster_id"], "answerability": question["answerability"],
            "delivered_sufficient": False if delivery_error else final["sufficient"],
            "semantic": final, "literal_coverage": span_assess(packets[final_id])["coverage"],
            "mapping_limitations": packets[final_id].get("limitations", []),
            "delivery_error": delivery_error, "error": trial.get("error"),
            "claim": review.get("status", "missing") if trial["arm"] == "review" else "disabled",
            "review_attempts": review.get("attempts", 0), "repairs": review.get("repairs", 0),
            "stop_reason": response.get("stop_reason", "no_response"),
            "first_eligible": first_eligible, "first_semantic": first,
            "first_to_final_evidence_changed": evidence_changed,
            "steps": trial.get("episode", {}).get("steps_used"), "duration_ms": trial.get("duration_ms"),
            "trial": trial,
        })
    return observations


def _quality(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter("unknown" if row["delivered_sufficient"] is None else
                     ("sufficient" if row["delivered_sufficient"] else "not_delivered_sufficient") for row in rows)
    total = len(rows)
    return {
        "scheduled_episodes": total, "confirmed_delivered_sufficient": counts["sufficient"],
        "known_not_delivered_sufficient": counts["not_delivered_sufficient"],
        "unknown_delivered_sufficiency": counts["unknown"],
        "delivery_failures": sum(row["delivery_error"] for row in rows),
        "unknown_semantic_assessments": sum(row["semantic"]["sufficient"] is None for row in rows),
        "confirmed_rate_lower_bound": ratio(counts["sufficient"], total),
        "possible_rate_upper_bound": ratio(counts["sufficient"] + counts["unknown"], total),
        "fully_observed_rate": ratio(counts["sufficient"], total) if not counts["unknown"] else None,
    }


def _macro_values(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    by_question: dict[str, list[Any]] = {}
    for row in rows:
        value = row["semantic"]["coverage"] if field == "semantic_coverage" else row[field]
        by_question.setdefault(row["question_id"], []).append(None if value is None else float(value))
    lower, upper, observed = [], [], []
    complete_questions = 0
    unknown = 0
    for values in by_question.values():
        known = [value for value in values if value is not None]
        unknown += len(values) - len(known)
        complete_questions += len(values) == len(known)
        lower.append(sum(known) / len(values))
        upper.append((sum(known) + len(values) - len(known)) / len(values))
        if known:
            observed.append(sum(known) / len(known))
    return {"question_count": len(by_question), "complete_questions": complete_questions,
            "known_episode_scores": len(rows) - unknown, "unknown_episode_scores": unknown,
            "question_macro_mean": mean(lower) if unknown == 0 else None,
            "question_macro_lower_bound": mean(lower), "question_macro_upper_bound": mean(upper),
            "question_macro_mean_over_observed_repeats": mean(observed),
            "observed_mean_caveat": "Conditional on available assessments; unknowns are not assigned zero or false."}


def _claims(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows or rows[0]["arm"] != "review":
        return None
    known_sufficient = [row for row in rows if not row["delivery_error"] and row["semantic"]["sufficient"] is True]
    known_insufficient = [row for row in rows if not row["delivery_error"] and row["semantic"]["sufficient"] is False]
    claims = [row for row in rows if row["claim"] == "sufficient"]
    false_sufficient = sum(row["claim"] == "sufficient" for row in known_insufficient)
    scored_claims = sum(row["semantic"]["sufficient"] is not None and not row["delivery_error"] for row in claims)
    unknown_claims = len(claims) - scored_claims
    false_insufficient = sum(row["claim"] == "insufficient" for row in known_sufficient)
    return {
        "statuses": dict(sorted(Counter(row["claim"] for row in rows).items())),
        "sufficient_claims": len(claims), "independently_scored_sufficient_claims": scored_claims,
        "unverified_sufficient_claims": unknown_claims,
        "false_sufficient": false_sufficient,
        "false_sufficient_per_scored_claim": ratio(false_sufficient, scored_claims),
        "false_sufficient_per_all_claims_lower_bound": ratio(false_sufficient, len(claims)),
        "false_sufficient_per_all_claims_upper_bound": ratio(false_sufficient + unknown_claims, len(claims)),
        "independently_insufficient_delivered_packets": len(known_insufficient),
        "false_sufficient_per_independently_insufficient_packet": ratio(false_sufficient, len(known_insufficient)),
        "false_insufficient": false_insufficient,
        "independently_sufficient_delivered_packets": len(known_sufficient),
        "false_insufficient_per_independently_sufficient_packet": ratio(false_insufficient, len(known_sufficient)),
        "insufficient_claims_with_unknown_independent_score": sum(row["claim"] == "insufficient" and row["semantic"]["sufficient"] is None for row in rows),
        "interpretation": "Unknown independent scores are excluded from scored denominators, never counted as passing claims. Baseline has no comparable sufficiency claim.",
    }


def _rescues(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows or rows[0]["arm"] != "review":
        return None
    eligible = [row for row in rows if row["first_eligible"]]
    incomplete = [row for row in eligible if row["first_semantic"]["sufficient"] is False]
    rescues = sum(row["delivered_sufficient"] is True for row in incomplete)
    unresolved = sum(row["delivered_sufficient"] is None for row in incomplete)
    attempted = [row for row in incomplete if row["repairs"] > 0]
    attempted_rescues = sum(row["delivered_sufficient"] is True for row in attempted)
    attempted_unknown = sum(row["delivered_sufficient"] is None for row in attempted)
    changed_rescues = sum(row["delivered_sufficient"] is True and row.get("first_to_final_evidence_changed") is True for row in attempted)
    return {
        "recorded_first_finish_episodes": len(eligible),
        "initially_insufficient_known": len(incomplete),
        "initially_sufficient_known": sum(row["first_semantic"]["sufficient"] is True for row in eligible),
        "unknown_initial_sufficiency": sum(row["first_semantic"]["sufficient"] is None for row in eligible),
        "initially_insufficient_with_correction_attempted": sum(row["repairs"] > 0 for row in incomplete),
        "confirmed_rescues": rescues, "unresolved_final_sufficiency": unresolved,
        "rescue_rate_lower_bound": ratio(rescues, len(incomplete)),
        "rescue_rate_upper_bound": ratio(rescues + unresolved, len(incomplete)),
        "fully_observed_rescue_rate": ratio(rescues, len(incomplete)) if unresolved == 0 else None,
        "correction_attempted_denominator": len(attempted),
        "confirmed_rescues_with_correction_attempted": attempted_rescues,
        "unknown_final_scores_with_correction_attempted": attempted_unknown,
        "correction_attempted_rescue_rate_lower_bound": ratio(attempted_rescues, len(attempted)),
        "correction_attempted_rescue_rate_upper_bound": ratio(attempted_rescues + attempted_unknown, len(attempted)),
        "fully_observed_correction_attempted_rescue_rate": ratio(attempted_rescues, len(attempted)) if attempted_unknown == 0 else None,
        "confirmed_rescues_with_correction_and_changed_evidence": changed_rescues,
        "sufficiency_flips_without_correction": sum(row["delivered_sufficient"] is True and row["repairs"] == 0 for row in incomplete),
        "sufficiency_flips_with_unchanged_evidence": sum(row["delivered_sufficient"] is True and row.get("first_to_final_evidence_changed") is False for row in incomplete),
        "eligibility": "Recorded first finish only: review attempts > 0 and at least two snapshots. This is not an independent estimate of budget eligibility for correction. The all-initially-insufficient rate describes first-to-final sufficiency flips, including episodes with no correction; actual correction attempts are reported separately. Unchanged-evidence flips may reflect evaluator variability rather than improved retrieval.",
    }


def arm_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    answerable = [row for row in rows if row["answerability"] == "answerable"]
    finished = [row for row in rows if row["stop_reason"] == "finished" and not row["delivery_error"]]
    return {
        "all_scheduled": _quality(rows), "answerable_only": _quality(answerable),
        "semantic_requirement_coverage": _macro_values(rows, "semantic_coverage"),
        "answerable_semantic_requirement_coverage": _macro_values(answerable, "semantic_coverage"),
        "literal_span_coverage": _macro_values(rows, "literal_coverage"),
        "review_claims": _claims(rows), "rescue": _rescues(rows),
        "stops": dict(sorted(Counter(row["stop_reason"] for row in rows).items())),
        "errors": dict(sorted(Counter((row["error"] or {}).get("type", "none") for row in rows).items())),
        "semantic_assessment_statuses": dict(sorted(Counter(row["semantic"]["status"] for row in rows).items())),
        "unknown_semantic_reasons": dict(sorted(Counter(row["semantic"]["reason"] for row in rows if row["semantic"]["sufficient"] is None).items())),
        "mapping_limitation_counts": dict(sorted(Counter(item["code"] for row in rows for item in row["mapping_limitations"]).items())),
        "finished_with_independently_insufficient_evidence": sum(row["semantic"]["sufficient"] is False for row in finished),
        "finished_with_unknown_sufficiency": sum(row["semantic"]["sufficient"] is None for row in finished),
        "steps": distribution([row["steps"] for row in rows]),
        "latency_ms": distribution([row["duration_ms"] for row in rows]),
        "episodes_over_180_seconds": sum(number(row["duration_ms"]) and row["duration_ms"] > 180_000 for row in rows),
        "episodes_over_210_seconds": sum(number(row["duration_ms"]) and row["duration_ms"] > 210_000 for row in rows),
        "provider": provider_metrics([row["trial"] for row in rows]),
    }


def paired_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    identities = sorted({row["question_id"] for row in rows})
    result = {}
    for field in ("delivered_sufficient", "semantic_coverage", "literal_coverage", "duration_ms", "steps"):
        per_question = []
        bounded = field in {"delivered_sufficient", "semantic_coverage", "literal_coverage"}
        for identity in identities:
            arms = {}
            for arm in ARMS:
                selected = [row for row in rows if row["question_id"] == identity and row["arm"] == arm]
                values = [row["semantic"]["coverage"] if field == "semantic_coverage" else row[field] for row in selected]
                known = [float(value) for value in values if value is not None and (number(value) or isinstance(value, bool))]
                arms[arm] = {"mean": mean(known) if len(known) == len(values) else None,
                             "known_repeats": len(known), "scheduled_repeats": len(values),
                             "lower_bound": sum(known) / len(values) if bounded else None,
                             "upper_bound": (sum(known) + len(values) - len(known)) / len(values) if bounded else None}
            complete = all(arms[arm]["mean"] is not None for arm in ARMS)
            per_question.append({"question_id": identity, **arms,
                                 "review_minus_baseline": arms["review"]["mean"] - arms["baseline"]["mean"] if complete else None,
                                 "delta_lower_bound": arms["review"]["lower_bound"] - arms["baseline"]["upper_bound"] if bounded else None,
                                 "delta_upper_bound": arms["review"]["upper_bound"] - arms["baseline"]["lower_bound"] if bounded else None})
        deltas = [item["review_minus_baseline"] for item in per_question if item["review_minus_baseline"] is not None]
        result[field] = {"question_count": len(per_question), "fully_scored_question_pairs": len(deltas),
                         "mean_paired_delta": mean(deltas) if len(deltas) == len(per_question) else None,
                         "mean_paired_delta_over_complete_questions": mean(deltas),
                         "mean_delta_lower_bound": mean([item["delta_lower_bound"] for item in per_question]) if bounded else None,
                         "mean_delta_upper_bound": mean([item["delta_upper_bound"] for item in per_question]) if bounded else None,
                         "per_question": per_question}
    return result


def group_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    arms = {arm: arm_summary([row for row in rows if row["arm"] == arm]) for arm in ARMS}
    base, reviewed = (arms[arm]["all_scheduled"] for arm in ARMS)
    gain = (reviewed["confirmed_delivered_sufficient"] - base["confirmed_delivered_sufficient"]
            if not base["unknown_delivered_sufficiency"] and not reviewed["unknown_delivered_sufficiency"] else None)
    base_cost, review_cost = (arms[arm]["provider"]["list_rate_estimate_usd"] for arm in ARMS)
    extra_cost = review_cost - base_cost if base_cost is not None and review_cost is not None else None
    return {"questions": len({row["question_id"] for row in rows}), "episodes": len(rows),
            "arms": arms, "paired": paired_metrics(rows),
            "answerable_only_paired": paired_metrics([row for row in rows if row["answerability"] == "answerable"]),
            "incremental_efficiency": {"additional_confirmed_sufficient_episodes": gain,
                "additional_list_rate_estimate_usd": extra_cost,
                "usd_per_additional_sufficient_episode": extra_cost / gain if gain is not None and gain > 0 and extra_cost is not None else None,
                "interpretation": "Defined only for positive fully observed sufficiency gain and complete provider usage and eligible dated pricing; descriptive, not causal population evidence."}}


def _fmt(value: Any, *, percent: bool = False) -> str:
    if value is None:
        return "unknown"
    return f"{100 * value:.1f}%" if percent else f"{value:,.3f}"


def markdown(summary: dict[str, Any]) -> str:
    overall = summary["overall"]
    lines = ["# Held-out evidence-review results", "",
             "Descriptive results for all 50 frozen held-out questions, three repeats and two arms (300 episodes). Repeats are averaged within questions. There are only two document families; no population significance claim or p-value is made.", "",
             "| Stratum | Baseline confirmed sufficient | Review confirmed sufficient | Paired sufficiency delta (percentage points) | Paired semantic coverage delta (percentage points) |",
             "|---|---:|---:|---:|---:|"]
    for name, group in [("All held-out", overall), *sorted(summary["families"].items())]:
        base, reviewed = (group["arms"][arm]["all_scheduled"] for arm in ARMS)
        lines.append(f"| {name} | {base['confirmed_delivered_sufficient']}/{base['scheduled_episodes']} | {reviewed['confirmed_delivered_sufficient']}/{reviewed['scheduled_episodes']} | {_fmt(None if group['paired']['delivered_sufficient']['mean_paired_delta'] is None else group['paired']['delivered_sufficient']['mean_paired_delta'] * 100)} | {_fmt(None if group['paired']['semantic_coverage']['mean_paired_delta'] is None else group['paired']['semantic_coverage']['mean_paired_delta'] * 100)} |")
    lines += ["", "Confirmed counts are lower bounds if semantic scores are unknown. Delivery failures remain in the scheduled denominator; unknown assessments are reported separately and are not treated as definite semantic failures.", "",
              "| Arm | Answerable sufficient | Unknown semantic scores | Delivery errors | Latency p50/p95 (s) | Observed real tokens | Complete usage | Estimated USD |",
              "|---|---:|---:|---:|---:|---:|---|---:|"]
    for arm in ARMS:
        row = overall["arms"][arm]
        answerable, latency, provider = row["answerable_only"], row["latency_ms"], row["provider"]
        p50 = latency["p50"] / 1000 if latency["p50"] is not None else None
        p95 = latency["p95"] / 1000 if latency["p95"] is not None else None
        lines.append(f"| {arm} | {answerable['confirmed_delivered_sufficient']}/{answerable['scheduled_episodes']} | {row['all_scheduled']['unknown_semantic_assessments']} | {row['all_scheduled']['delivery_failures']} | {_fmt(p50)}/{_fmt(p95)} | {provider['observed_tokens']['total_tokens']:,} | {str(provider['usage_complete']).lower()} | {_fmt(provider['list_rate_estimate_usd'])} |")
    claims = overall["arms"]["review"]["review_claims"]
    rescues = overall["arms"]["review"]["rescue"]
    efficiency = overall["incremental_efficiency"]
    lines += ["", f"Review made {claims['sufficient_claims']} sufficient claims: {claims['false_sufficient']} independently false among {claims['independently_scored_sufficient_claims']} scored claims, with {claims['unverified_sufficient_claims']} unverified claims. False-insufficient decisions: {claims['false_insufficient']} among {claims['independently_sufficient_delivered_packets']} independently sufficient delivered packets.", "",
              f"Observed first-to-final sufficiency flips: {rescues['confirmed_rescues']} among {rescues['initially_insufficient_known']} recorded initially insufficient first finishes. Among {rescues['correction_attempted_denominator']} actual correction attempts, {rescues['confirmed_rescues_with_correction_attempted']} became sufficient, including {rescues['confirmed_rescues_with_correction_and_changed_evidence']} with changed evidence. This is not an independent budget-eligibility estimate; {rescues['sufficiency_flips_with_unchanged_evidence']} unchanged-evidence flips may reflect evaluator variability. Initial unknown scores: {rescues['unknown_initial_sufficiency']}; relevant final unknown scores: {rescues['unresolved_final_sufficiency']}. Incremental estimated USD per additional sufficient delivery: {_fmt(efficiency['usd_per_additional_sufficient_episode'])}.", "",
              f"Offline semantic evaluation is separate: {summary['offline_semantic_evaluation']['all_assessments']['calls']} real provider calls, estimated USD {_fmt(summary['offline_semantic_evaluation']['all_assessments']['list_rate_estimate_usd'])}; none of this cost is added to retrieval overhead. All three explicit semantic negative controls passed.", "",
              "Costs are list-rate estimates, not bills. Only calls dated 2026-10-10 UTC use the Saturday off-peak rates: USD 0.003 per million cached input tokens, 0.15 per million uncached input tokens, and 0.6 per million output tokens. Missing usage or other dates leave total cost unknown; observed cache hits and misses are retained separately in summary.json.", "",
              "The corpus is deterministic text derived from four checked-in documents. Both arms receive the known document scope. This tests the production retrieval core and tools on PGlite; it does not measure PDF/image understanding, document discovery, HTTP/API workers, native PostgreSQL concurrency or production traffic. The judge uses a separate blind prompt and frozen gold, but shares the DeepSeek model family with the agent, so correlated errors remain possible. Literal quote coverage is not semantic correctness.", "",
              "Equal initial production budgets do not imply identical hard execution ceilings: legacy baseline forced finishes/retries and actual overruns are retained. Development infrastructure failures and synthetic calibration are excluded from held-out benefit metrics. Detailed stops, errors, steps, latency, unknowns, source-mapping limitations, question-level paired deltas and provider accounting are in summary.json.", ""]
    return "\n".join(lines)


def summarize(args: argparse.Namespace) -> dict[str, Any]:
    from score import negative_control_passed
    gold = json.loads(args.gold.read_text())
    raw_trials = [trial for path in args.trials for trial in read_lines(path)]
    questions, trials, excluded = validate_schedule(raw_trials, gold)
    paths = {name: args.assessments / name for name in
             ("trial-packets.jsonl", "blind-packets.jsonl", "assessments.jsonl")}
    mappings = unique_index(read_lines(paths["trial-packets.jsonl"]), "trial_id", "packet mapping")
    packets = unique_index(read_lines(paths["blind-packets.jsonl"]), "packet_sha256", "blind packet")
    assessments = unique_index(read_lines(paths["assessments.jsonl"]), "id", "assessment")
    controls = [assessments.get(f"negative-control-{index}") for index in range(3)]
    if any(record is None or record.get("negative_control") is not True
           or record.get("negative_control_passed") is not True
           or not negative_control_passed(record.get("semantic", {})) for record in controls):
        raise ValueError("Three completed passing semantic negative controls are required")
    observations = build_observations(trials, questions, mappings, packets, assessments)
    held_out_ids = {mappings[trial["id"]][kind] for trial in trials
                    for kind in ("final_packet", "first_packet") if mappings[trial["id"]].get(kind)}
    control_ids = {f"negative-control-{index}" for index in range(3)}
    failures = [trial["id"] for trial in trials if any(value is not True for value in trial.get("gates", {}).values())]
    input_paths = [args.gold, *args.trials, *paths.values()]
    summary = {
        "schema_version": "knowhere-held-out-benefit-summary/1",
        "validation": {"expected_questions": 50, "repeats": 3, "arms": list(ARMS),
                       "expected_episodes": 300, "actual_episodes": len(trials),
                       "protocol_digest": trials[0]["protocol_digest"],
                       "negative_controls_passed": 3, "runtime_gate_failure_trial_ids": failures,
                       "excluded_development_episodes": len(excluded),
                       "excluded_development_errors": sum(trial.get("error") is not None for trial in excluded),
                       "input_sha256": {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in input_paths}},
        "inference": {"unit": "Question, averaging its three repeats before pairing arms",
                      "held_out_document_families": 2,
                      "population_significance_claim": False, "p_value": None,
                      "confidence_interval": None,
                      "interpretation": "Descriptive within-corpus paired results only; two document families cannot establish production generalization."},
        "overall": group_summary(observations),
        "families": {family: group_summary([row for row in observations if row["family"] == family])
                     for family in sorted({row["family"] for row in observations})},
        "offline_semantic_evaluation": {
            "all_assessments": provider_metrics(list(assessments.values())),
            "held_out_unique_packet_assessments": provider_metrics([assessments[identity] for identity in sorted(held_out_ids)]),
            "negative_controls": provider_metrics([assessments[identity] for identity in sorted(control_ids)]),
            "other_assessments": provider_metrics([record for identity, record in assessments.items() if identity not in held_out_ids | control_ids]),
            "separate_from_retrieval_cost": True,
        },
        "case_audit": [{key: value for key, value in row.items() if key != "trial"} for row in observations],
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    (args.output / "RESULTS.md").write_text(markdown(summary))
    return summary


def self_test() -> None:
    """Small in-memory metric checks, deliberately never written as experiment results."""
    usage = {"prompt_tokens": 300, "completion_tokens": 20, "total_tokens": 320,
             "prompt_cache_hit_tokens": 100, "prompt_cache_miss_tokens": 200}
    call = {"requested_model": "deepseek-flash", "returned_model": "deepseek-flash",
            "started_at": "2026-10-10T12:00:00+00:00", "usage": usage, "kind": "explorer", "status": "response"}
    record = {"provider_calls": [call], "provider_usage": {"usage_complete": True}}
    metrics = provider_metrics([record])
    assert abs(metrics["list_rate_estimate_usd"] - 0.0000423) < 1e-12
    assert metrics["observed_tokens"]["total_tokens"] == 320
    unknown_date = {**record, "provider_calls": [{**call, "started_at": "2026-10-11T00:00:00Z"}]}
    assert provider_metrics([unknown_date])["list_rate_estimate_usd"] is None
    assert provider_metrics([{**record, "provider_usage": {"usage_complete": False}}])["list_rate_estimate_usd"] is None
    rows = []
    for question in ("micron-1", "spacex-1"):
        for repeat in range(3):
            for arm in ARMS:
                success = question == "micron-1" and (arm == "review" or repeat == 2)
                rows.append({"question_id": question, "arm": arm, "delivered_sufficient": success,
                             "semantic": {"coverage": float(success)}, "literal_coverage": float(success),
                             "duration_ms": 1000, "steps": 2})
    paired = paired_metrics(rows)
    assert abs(paired["delivered_sufficient"]["mean_paired_delta"] - 1 / 3) < 1e-12
    rows[0]["delivered_sufficient"] = None
    paired = paired_metrics(rows)
    assert paired["delivered_sufficient"]["mean_paired_delta"] is None
    assert paired["delivered_sufficient"]["fully_scored_question_pairs"] == 1
    assert paired["delivered_sufficient"]["mean_delta_lower_bound"] <= paired["delivered_sufficient"]["mean_delta_upper_bound"]
    rescue_rows = [{"arm": "review", "first_eligible": True, "first_semantic": {"sufficient": False},
                    "delivered_sufficient": True, "repairs": repairs,
                    "first_to_final_evidence_changed": bool(repairs)} for repairs in (0, 1)]
    rescue = _rescues(rescue_rows)
    assert rescue["confirmed_rescues"] == 2
    assert rescue["correction_attempted_denominator"] == 1
    assert rescue["confirmed_rescues_with_correction_attempted"] == 1
    assert rescue["sufficiency_flips_without_correction"] == 1
    assert rescue["confirmed_rescues_with_correction_and_changed_evidence"] == 1
    gold = {"questions": [{"id": question, "split": "held_out", "cluster_id": question.split("-")[0] + "/case"}
                           for question in ("micron-1", "spacex-1")]}
    trials = [{"id": f"{question['id']}:{repeat}:{arm}", "question_id": question["id"], "split": "held_out",
               "repeat": repeat, "arm": arm, "protocol_digest": "self-test-only"}
              for question in gold["questions"] for repeat in range(3) for arm in ARMS]
    assert len(validate_schedule(trials, gold, expected_questions=2)[1]) == 12
    for bad in (trials[:-1], trials + [trials[0]]):
        try:
            validate_schedule(bad, gold, expected_questions=2)
        except ValueError:
            pass
        else:
            raise AssertionError("Missing or duplicate trial was accepted")
    print("Self-test passed: schedule completeness, paired question means, unknowns, and dated real-usage cost. No experiment report was produced.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=Path, nargs="+")
    parser.add_argument("--assessments", type=Path)
    parser.add_argument("--gold", type=Path, default=GOLD)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    arguments = parser.parse_args()
    if arguments.self_test:
        self_test()
    else:
        if not arguments.trials or arguments.assessments is None or arguments.output is None:
            parser.error("--trials, --assessments and --output are required")
        result = summarize(arguments)
        print(json.dumps({"episodes": result["validation"]["actual_episodes"],
                          "questions": result["validation"]["expected_questions"],
                          "families": list(result["families"]), "output": str(arguments.output)}))
