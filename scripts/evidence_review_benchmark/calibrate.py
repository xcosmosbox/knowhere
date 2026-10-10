"""Real DeepSeek reviewer calibration; explorer and corpus remain scripted."""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
from pathlib import Path

from runtime import MODEL, ROOT, ProviderObserver, prepare_environment, provider_override, usage_summary


async def run(args: argparse.Namespace) -> None:
    spec = importlib.util.spec_from_file_location("controlled_experiment", ROOT / "scripts/experiment_evidence_review.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from shared.services.ai.llm_overrides import reset_llm_overrides_async, set_llm_overrides_async
    fixture = json.loads(module.FIXTURES.read_text())
    cases = [case for case in fixture["cases"] if case["case_id"] not in module.LIVE_EXCLUDED]
    observer = ProviderObserver()
    observer.install()
    token = set_llm_overrides_async(provider_override())
    trials = []
    args.output.mkdir(parents=True, exist_ok=True)
    checkpoint = args.output / "reviewer-calibration-trials.jsonl"
    if checkpoint.exists():
        raise FileExistsError("Use a new output directory; calibration trials are never silently overwritten")
    try:
        with checkpoint.open("x") as stream:
            for repeat in range(args.repeats):
                for index, case in enumerate(cases):
                    order = (False, True) if (index + repeat) % 2 == 0 else (True, False)
                    trial = {"case_id": case["case_id"], "repeat": repeat, "answerable": case["answerable"],
                             "negative_control": False, "order": ["review" if enabled else "baseline" for enabled in order]}
                    offset = len(observer.records)
                    for enabled in order:
                        observer.trial_id = f"{case['case_id']}:{repeat}:{enabled}"
                        arm = await module.run_arm(case, enabled=enabled, mode="live-reviewer")
                        trial[arm["variant"]] = arm
                    trial["provider_calls"] = observer.records[offset:]
                    trials.append(trial)
                    stream.write(json.dumps(trial, ensure_ascii=False) + "\n")
                    stream.flush()
                    print(json.dumps({"completed_pairs": len(trials), "case": case["case_id"],
                                      "repeat": repeat, "review_status": trial["review"]["review_status"]}), flush=True)
        report = {"schema_version": "knowhere-live-calibration/1", "model": MODEL,
                  "claim_scope": "Only reviewer calls are real. Explorer/corpus and explorer token counts are scripted; no end-to-end benefit inference.",
                  "fixture_sha256": module.digest(fixture), "repeats": args.repeats,
                  "summary": module.aggregate(trials), "provider_usage": usage_summary(observer.records), "trials": trials}
        (args.output / "reviewer-calibration.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    finally:
        reset_llm_overrides_async(token)
        await observer.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    prepare_environment(arguments.key_file)
    asyncio.run(run(arguments))
