"""Revision-pinned, real-tool paired retrieval benchmark (no scripted explorer).

Uses the production core route and public projection. HTTP authentication,
Redis response cache, billing, uploads and parser workers are outside its scope.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from runtime import (MODEL, ROOT, EpisodeObserver, ProviderObserver, digest,
                     prepare_environment, provider_override, usage_summary, utc_now)

OUTER_DEADLINE_SECONDS = 210
GOLD = ROOT / "scripts/fixtures/evidence_review_live_gold.json"
def runtime_sources() -> list[str]:
    paths = list((ROOT / "packages/shared-python/shared").rglob("*.py"))
    paths += list((ROOT / "apps/api/alembic").rglob("*.py"))
    paths += list((ROOT / "scripts/evidence_review_benchmark").glob("*.py"))
    paths += [ROOT / path for path in (
        "pyproject.toml", "uv.lock", "packages/shared-python/pyproject.toml",
        "scripts/evidence_review_benchmark/pglite/run-with-pglite.mjs",
        "scripts/evidence_review_benchmark/pglite/package.json",
        "scripts/evidence_review_benchmark/pglite/package-lock.json",
    )]
    return sorted(str(path.relative_to(ROOT)) for path in paths)


def freeze(gold: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    schedule = []
    for split, repeats in (("development", 1), ("held_out", 3)):
        questions = [question for question in gold["questions"] if question["split"] == split]
        for repeat in range(repeats):
            for index, question in enumerate(questions):
                order = ["baseline", "review"] if (repeat + index) % 2 == 0 else ["review", "baseline"]
                schedule.append({"question_id": question["id"], "split": split, "repeat": repeat,
                                 "question_index": index, "order": order})
    return {
        "schema_version": "knowhere-live-protocol/1", "created_at": utc_now(),
        "feature_revision": "f68cee2d2793dc4d6fa5cb9281f3d6d357826b1b",
        "git_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "python_version": platform.python_version(),
        "library_versions": {name: importlib.metadata.version(name) for name in (
            "openai", "httpx", "asyncpg", "SQLAlchemy", "psycopg2-binary", "rank-bm25", "jieba", "numpy", "alembic",
        )},
        "model": MODEL, "thinking": "disabled", "temperature": 0,
        "max_completion_tokens": 1024, "episode_max_steps": 15, "episode_wall_clock_seconds": 180,
        "common_outer_deadline_seconds": OUTER_DEADLINE_SECONDS, "review_calls_max": 2, "corrections_max": 1,
        "held_out_execution": {"logical_shards": 7, "max_concurrent_workers": 7,
                               "isolation": "one database and durable output directory per worker"},
        "gold_sha256": hashlib.sha256(GOLD.read_bytes()).hexdigest(),
        "corpus_digest": manifest["corpus_digest"], "index_input_digest": manifest["index_input_digest"],
        "runtime_source_sha256": {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in runtime_sources()},
        "revision_pins": manifest["revision_pins"], "schedule": schedule,
        "scope": "Real published derived text corpus, real OpenAIHarness, production corpus tools and public evidence projection. PGlite SQL/index semantics; not HTTP, parser, image/PDF, native PostgreSQL concurrency or production traffic evaluation.",
        "cache_policy": "Application response cache bypassed by calling production core route directly; no synthetic model/tool results. Local index caches may warm within each worker. Redis readiness notifications are unavailable and fail open through existing production handling. Provider prefix cache remains enabled and measured; arm order alternates.",
        "document_scope_policy": "Both arms receive the same known-document include_document_ids scope from the frozen question inventory. This measures retrieval within a selected document set, not document discovery across a whole account.",
        "failure_policy": "Record every scheduled episode once, including provider errors and timeouts. Never replace poor outcomes. Resume only missing trial IDs against the exact frozen input digests.",
        "interruption_policy": "Durable started journal precedes each request. Started episodes without final records become interrupted/unknown failures on resume and are never resent. Stop a worker after outer response timeout because cancelling a synchronous provider thread cannot prove server-side cancellation.",
        "budget_caveat": "Equal initial production settings, not equal hard execution ceilings. Baseline may make a forced finish after step 15 and retries synchronous calls. Review shares the original budget and disables retries. The 210-second outer response timeout stops the worker; late provider resource use can remain unknown.",
        "inference_policy": "Exploratory document-family benchmark; three repeats are not independent questions. Only two held-out document families; no population-wide significance claim.",
    }


async def retrieve(question: dict[str, Any], manifest: dict[str, Any], enabled: bool) -> dict[str, Any]:
    from shared.core.database import get_db_context
    from shared.services.retrieval.corpus_revision_context import CorpusRevisionContext
    from shared.services.retrieval.execution.query_request import RetrievalQuery
    from shared.services.retrieval.execution.response_projection import project_public_retrieval_response
    from shared.services.retrieval.execution.revision_pins import capture_revision_pins
    from shared.services.retrieval.execution.routes import run_retrieval_route
    scoped = [doc["document_id"] for doc in manifest["documents"] if doc["doc_key"] in question["doc_keys"]]
    if len(scoped) != len(question["doc_keys"]):
        raise ValueError("Question document scope does not match frozen corpus")
    async with get_db_context() as db:
        pins = await capture_revision_pins(db, user_id=manifest["user_id"], namespace=manifest["namespace"])
        if dict(pins) != manifest["revision_pins"]:
            raise ValueError("Active document revisions differ from frozen revisions")
        request = RetrievalQuery.from_parameters(
            db=db, user_id=manifest["user_id"], namespace=manifest["namespace"],
            query=question["query"], top_k=1, exclude_document_ids=[], exclude_sections=[],
            include_document_ids=scoped, use_agentic=True, review_evidence=enabled,
        )
        context = request.build_route_context()
        with CorpusRevisionContext.bind(pins):
            outcome = await run_retrieval_route(replace(context, revision_pins=pins))
        return await project_public_retrieval_response(outcome.response)


def production_budget_within_bounds(
    episode: dict[str, Any], review: dict[str, Any], *, review_enabled: bool,
) -> bool:
    """Check the frozen initial limits and the production correction policy.

    A correction may tighten the original 15-step cap to the charged steps at
    that decision plus four. Reconstruct that boundary from the observed trace:
    multiple tools in one explorer round cost one step, picks cost no steps,
    and reviewer attempts share the same budget. This never changes an episode.
    """
    initial = episode.get("initial_max_steps")
    final = episode.get("final_max_steps")
    used = episode.get("steps_used")
    if (
        type(initial) is not int or type(final) is not int or type(used) is not int
        or initial != 15
        or episode.get("initial_wall_clock_seconds") != 180
        or not 1 <= final <= initial
        or used < 0
    ):
        return False
    if not review_enabled:
        # The unchanged baseline can make one final forced-finish call.
        return final == initial and used <= initial + 1
    repairs = review.get("repairs", 0)
    attempts = review.get("attempts", 0)
    if (
        used > final
        or type(repairs) is not int or repairs not in (0, 1)
        or type(attempts) is not int or not 0 <= attempts <= 2
    ):
        return False
    if repairs == 0:
        return final == initial

    steps = episode.get("steps")
    if not isinstance(steps, list):
        return False
    rounds: set[int] = set()
    for step in steps:
        if not isinstance(step, dict):
            return False
        name = step.get("tool_name")
        if name == "corpus.pick":
            continue
        if name != "evidence_review":
            round_index = step.get("round_index")
            if type(round_index) is not int or round_index < 1:
                return False
            rounds.add(round_index)
            continue
        try:
            assessment = json.loads(step["observation_text"])
        except (KeyError, TypeError, ValueError):
            return False
        if not isinstance(assessment, dict):
            return False
        if assessment.get("repairs") != 1:
            continue
        prior_attempts = assessment.get("attempts")
        if (
            assessment.get("status") != "insufficient"
            or type(prior_attempts) is not int
            or not 0 <= prior_attempts <= min(1, attempts)
        ):
            return False
        # Production can request correction without an LLM call when the first
        # snapshot is empty. No requirements have been frozen on that path.
        if prior_attempts == 0 and (
            assessment.get("reason") != "No final-visible evidence was selected."
            or assessment.get("coverage") != []
        ):
            return False
        boundary = len(rounds) + prior_attempts
        return (
            0 < boundary < initial and boundary <= used
            and final == min(initial, boundary + 4)
        )
    return False


async def run_trial(question: dict[str, Any], manifest: dict[str, Any], scheduled: dict[str, Any],
                    arm: str, provider: ProviderObserver, protocol_digest: str) -> dict[str, Any]:
    trial_id = f"{question['id']}:{scheduled['repeat']}:{arm}"
    provider.trial_id = trial_id
    offset = len(provider.records)
    observation = EpisodeObserver()
    observation.install()
    started = time.perf_counter()
    result: dict[str, Any] = {"id": trial_id, "question_id": question["id"], "repeat": scheduled["repeat"],
                              "arm": arm, "split": question["split"], "started_at": utc_now(),
                              "revision_pins": manifest["revision_pins"],
                              "protocol_digest": protocol_digest, "error": None, "response": None}
    try:
        async with asyncio.timeout(OUTER_DEADLINE_SECONDS):
            result["response"] = await retrieve(question, manifest, arm == "review")
    except Exception as exc:
        result["error"] = {"type": type(exc).__name__,
                           "reason": "common_outer_deadline" if isinstance(exc, TimeoutError) else "episode_failed"}
    finally:
        observation.restore()
    result.update(duration_ms=round((time.perf_counter() - started) * 1000, 3), ended_at=utc_now(),
                  episode=observation.episode, snapshots=observation.snapshots,
                  provider_calls=provider.records[offset:])
    result["provider_usage"] = usage_summary(result["provider_calls"])
    response = result["response"] or {}
    review = response.get("evidence_review", {})
    episode = result["episode"]
    result["gates"] = {
        "production_limits_unchanged": production_budget_within_bounds(
            episode, review, review_enabled=arm == "review",
        ),
        "real_requested_model": all(call["requested_model"] == MODEL for call in result["provider_calls"]),
        "returned_model_matches": all(call.get("returned_model", MODEL) == MODEL for call in result["provider_calls"]),
        "agentic_route": result["error"] is not None or response.get("router_used") == "agent_explore",
        "bounded_review": int(review.get("attempts", 0)) <= 2 and int(review.get("repairs", 0)) <= 1
            and sum(call["kind"] == "reviewer" for call in result["provider_calls"]) <= 2,
        "real_explorer": result["error"] is not None or any(call["kind"] == "explorer" for call in result["provider_calls"]),
        "disabled_has_no_review": arm != "baseline" or (not review and not result["snapshots"]
            and all(call["kind"] != "reviewer" for call in result["provider_calls"])),
        "review_step_cap": arm != "review" or episode.get("steps_used", 0) <= 15,
    }
    return result


async def run(args: argparse.Namespace) -> None:
    from corpus import migrate_database, prepare_corpus, seed_corpus
    gold = json.loads(GOLD.read_text())
    manifest = prepare_corpus(ROOT, GOLD)
    args.output.mkdir(parents=True, exist_ok=True)
    if args.freeze:
        protocol = freeze(gold, manifest)
        with args.protocol.open("x") as stream:
            json.dump(protocol, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        print(json.dumps({"status": "frozen", "gold_sha256": protocol["gold_sha256"],
                          "corpus_digest": manifest["corpus_digest"], "scheduled_pairs": len(protocol["schedule"])}))
        return
    protocol = json.loads(args.protocol.read_text())
    current = freeze(gold, manifest)
    for field in ("gold_sha256", "corpus_digest", "index_input_digest", "runtime_source_sha256", "schedule", "revision_pins", "python_version", "library_versions"):
        if protocol[field] != current[field]:
            raise ValueError(f"Frozen protocol mismatch: {field}")
    protocol_digest = digest(protocol)
    migrate_database(ROOT)
    verification = await seed_corpus(manifest)
    (args.output / "index-verification.json").write_text(json.dumps(verification, indent=2) + "\n")
    from shared.services.ai.llm_overrides import reset_llm_overrides_async, set_llm_overrides_async
    observer = ProviderObserver(args.output / "provider-events.jsonl")
    observer.install()
    override = set_llm_overrides_async(provider_override())
    questions = {question["id"]: question for question in gold["questions"]}
    checkpoint = args.output / "trials.jsonl"
    done = {}
    if checkpoint.exists():
        for line in checkpoint.read_text().splitlines():
            previous = json.loads(line)
            if previous["protocol_digest"] != protocol_digest or previous["id"] in done:
                raise ValueError("Checkpoint provenance mismatch or duplicate trial")
            done[previous["id"]] = previous
    journal = args.output / "started.jsonl"
    started_trials = {}
    if journal.exists():
        for line in journal.read_text().splitlines():
            entry = json.loads(line)
            if entry["protocol_digest"] != protocol_digest or entry["id"] in started_trials:
                raise ValueError("Started journal provenance mismatch or duplicate")
            started_trials[entry["id"]] = entry
    try:
        with checkpoint.open("a") as stream, journal.open("a") as starts:
            for trial_id, entry in started_trials.items():
                if trial_id not in done:
                    interrupted = {**entry, "error": {"type": "InterruptedTrial", "reason": "started_without_final_record"},
                                   "response": None, "duration_ms": None, "episode": {}, "snapshots": [],
                                   "provider_calls": [], "provider_usage": {"usage_complete": False},
                                   "gates": {"interrupted_not_retried": True}, "ended_at": None,
                                   "revision_pins": manifest["revision_pins"]}
                    stream.write(json.dumps(interrupted) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                    done[trial_id] = interrupted
            for scheduled in protocol["schedule"]:
                if scheduled["split"] != args.split or scheduled["question_index"] % args.shards != args.shard:
                    continue
                if args.question and scheduled["question_id"] not in args.question:
                    continue
                for arm in scheduled["order"]:
                    trial_id = f"{scheduled['question_id']}:{scheduled['repeat']}:{arm}"
                    if trial_id in done:
                        continue
                    entry = {"id": trial_id, "question_id": scheduled["question_id"],
                             "repeat": scheduled["repeat"], "arm": arm, "split": scheduled["split"],
                             "protocol_digest": protocol_digest, "started_at": utc_now()}
                    starts.write(json.dumps(entry) + "\n")
                    starts.flush()
                    os.fsync(starts.fileno())
                    result = await run_trial(questions[scheduled["question_id"]], manifest, scheduled,
                                             arm, observer, protocol_digest)
                    stream.write(json.dumps(result, ensure_ascii=False) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                    done[trial_id] = result
                    print(json.dumps({"completed": len(done), "trial": trial_id, "error": result["error"],
                                      "stop": (result["response"] or {}).get("stop_reason"),
                                      "milliseconds": result["duration_ms"], "gates": result["gates"]}), flush=True)
                    if not all(result["gates"].values()):
                        raise RuntimeError("Runtime policy gate failed; retained episode and stopped shard")
                    if (result["error"] or {}).get("reason") == "common_outer_deadline":
                        raise RuntimeError("Outer response deadline retained; stop worker before another episode")
    finally:
        reset_llm_overrides_async(override)
        await observer.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--split", choices=("development", "held_out"), default="development")
    parser.add_argument("--question", action="append")
    parser.add_argument("--shards", type=int, default=1)
    parser.add_argument("--shard", type=int, default=0)
    arguments = parser.parse_args()
    if arguments.shards < 1 or not 0 <= arguments.shard < arguments.shards:
        parser.error("Invalid shard")
    if arguments.question and arguments.split != "development":
        parser.error("Question selection is only allowed for development smoke checks")
    prepare_environment(arguments.key_file)
    asyncio.run(run(arguments))
