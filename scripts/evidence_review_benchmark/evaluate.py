"""Offline arm-blinded semantic assessment, separate from retrieval cost/budgets."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from runtime import BASE_URL, ROOT, ProviderObserver, digest, prepare_environment, usage_summary, utc_now
from resources import PROFILES, resource_spec, scorer_client


def read_lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def append_line(path: Path, value: dict[str, Any]) -> None:
    with path.open("a") as stream:
        stream.write(json.dumps(value, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


async def run(args: argparse.Namespace) -> None:
    from openai import AsyncOpenAI
    from shared.services.http.client_pool import get_async_client
    from corpus import prepare_corpus
    from score import (build_blinded_packet, build_snapshot_packet, negative_control_passed,
                       semantic_assess, semantic_negative_control, span_assess)
    gold_path = args.gold
    gold = json.loads(gold_path.read_text())
    manifest = prepare_corpus(ROOT, gold_path)
    questions = {question["id"]: question for question in gold["questions"]}
    args.output.mkdir(parents=True, exist_ok=True)
    protocol = json.loads(args.protocol.read_text()) if args.protocol else None
    citation_mode = args.citation_mode or (protocol or {}).get("evaluation", {}).get("citation_mode", "exact-quotes")
    if protocol and (protocol["gold_sha256"] != hashlib.sha256(gold_path.read_bytes()).hexdigest()
                     or protocol["resources"] != resource_spec(args.resource_profile)
                     or protocol["corpus_digest"] != manifest["corpus_digest"]):
        raise ValueError("Scoring inventory/resources differ from frozen retrieval protocol")
    if protocol and (protocol.get("evaluation", {}).get("citation_mode", "exact-quotes") != citation_mode
                     or protocol["runtime_source_sha256"]["scripts/evidence_review_benchmark/score.py"] != hashlib.sha256((ROOT / 'scripts/evidence_review_benchmark/score.py').read_bytes()).hexdigest()):
        raise ValueError("Scorer mode/source differ from the frozen retrieval protocol")
    evaluation_spec = {"gold_sha256": hashlib.sha256(gold_path.read_bytes()).hexdigest(),
                       "resources": resource_spec(args.resource_profile),
                       "retrieval_protocol_digest": digest(protocol) if protocol else None,
                       "citation_mode": citation_mode,
                       "scorer_sha256": hashlib.sha256((ROOT / 'scripts/evidence_review_benchmark/score.py').read_bytes()).hexdigest()}
    spec_path = args.output / 'evaluation-protocol.json'
    if spec_path.exists() and json.loads(spec_path.read_text()) != evaluation_spec:
        raise ValueError("Frozen scoring protocol mismatch")
    spec_path.write_text(json.dumps(evaluation_spec, indent=2) + '\n')
    packets: dict[str, dict[str, Any]] = {}
    mappings = []
    for path in args.trials:
        for trial in read_lines(path):
            if protocol and trial["protocol_digest"] != digest(protocol):
                raise ValueError("Trial does not belong to the frozen retrieval protocol")
            question = questions[trial["question_id"]]
            packet = build_blinded_packet(trial, question, manifest)
            identity = packet["packet_sha256"]
            packets[identity] = packet
            mapping = {"trial_id": trial["id"], "final_packet": identity,
                       "delivery_error": trial.get("error"), "first_packet": None}
            review = (trial.get("response") or {}).get("evidence_review", {})
            if review.get("attempts", 0) > 0 and len(trial.get("snapshots", [])) >= 2:
                first = build_snapshot_packet(trial["snapshots"][0], question, manifest)
                packets[first["packet_sha256"]] = first
                mapping["first_packet"] = first["packet_sha256"]
            mappings.append(mapping)
    for name, records in (("blind-packets.jsonl", list(packets.values())), ("trial-packets.jsonl", mappings)):
        target = args.output / name
        expected = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
        if target.exists() and target.read_text() != expected:
            raise ValueError("Scoring input changed; use a new output directory")
        target.write_text(expected)
    observer = ProviderObserver()
    observer.install()
    client = AsyncOpenAI(api_key=os.environ["DS_KEY"], base_url=BASE_URL, max_retries=0,
                         timeout=30, http_client=get_async_client())
    client = scorer_client(client, args.resource_profile)
    results_path, started_path = args.output / "assessments.jsonl", args.output / "started.jsonl"
    results = {record["id"]: record for record in read_lines(results_path)}
    for record in read_lines(started_path):
        if record["id"] not in results:
            failed = {**record, "semantic": {"status": "error", "reason_code": "interrupted_assessment",
                      "all_supported": None, "semantic_coverage": None}, "provider_calls": [],
                      "provider_usage": {"usage_complete": False}, "duration_ms": None}
            append_line(results_path, failed)
            results[record["id"]] = failed
    semaphore = asyncio.Semaphore(args.concurrency)

    async def assess(identity: str, packet: dict[str, Any], control: bool = False) -> dict[str, Any]:
        if identity in results:
            return results[identity]
        async with semaphore:
            observer.trial_id = identity
            started = {"id": identity, "input_digest": digest(packet), "started_at": utc_now(), "negative_control": control}
            append_line(started_path, started)
            begin = time.perf_counter()
            semantic = await semantic_assess(packet["query"], packet["gold_requirements"], packet["evidence_items"], client, citation_mode=citation_mode)
            calls = [record for record in observer.records if record["trial_id"] == identity]
            result = {**started, "semantic": semantic, "provider_calls": calls,
                      "provider_usage": usage_summary(calls), "ended_at": utc_now(),
                      "duration_ms": round((time.perf_counter() - begin) * 1000, 3)}
            if control:
                result["negative_control_passed"] = negative_control_passed(semantic)
            else:
                result["span"] = span_assess(packet)
            append_line(results_path, result)
            results[identity] = result
            print(json.dumps({"assessed": len(results), "id": identity[:16], "status": semantic["status"],
                              "all_supported": semantic["all_supported"], "negative_control": control}), flush=True)
            return result
    try:
        control = semantic_negative_control()
        control_results = await asyncio.gather(*(assess(f"negative-control-{index}", control, True) for index in range(3)))
        if not all(result.get("negative_control_passed") for result in control_results):
            raise RuntimeError("Blind semantic negative control failed; retain results and stop scoring")
        await asyncio.gather(*(assess(identity, packet) for identity, packet in sorted(packets.items())))
        summary = {"unique_packets": len(packets), "trial_mappings": len(mappings),
                   "negative_controls_passed": 3,
                   "invalid_assessments": sum(result["semantic"]["status"] != "valid" for result in results.values()),
                   "evaluator_provider_usage": usage_summary([call for result in results.values() for call in result["provider_calls"]]),
                   "claim_scope": "Independent prompt with frozen gold, blinded to arm and production verdict; automated model assessment, not human ground truth. Repeated identical packets reuse one assessment. Offline evaluator cost is separate from retrieval cost."}
        (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    finally:
        await observer.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--gold", type=Path, default=ROOT / "scripts/fixtures/evidence_review_live_gold.json")
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--resource-profile", choices=PROFILES, default="production")
    parser.add_argument("--citation-mode", choices=("exact-quotes", "source-spans"))
    parser.add_argument("--trials", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--concurrency", type=int, default=4)
    arguments = parser.parse_args()
    if arguments.concurrency < 1:
        parser.error("--concurrency must be positive")
    prepare_environment(arguments.key_file)
    asyncio.run(run(arguments))
