"""Posthoc cross-model sensitivity analysis; never overwrite frozen model scores."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

from score import validate_semantic_assessment


def lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def run(base: Path) -> dict:
    evaluation = base / "heldout-evaluation"
    packet_path = evaluation / "blind-packets.jsonl"
    packets = {row["packet_sha256"]: row for row in lines(packet_path)}
    assessments = {row["id"]: row for row in lines(evaluation / "assessments.jsonl")}
    mappings = {row["trial_id"]: row for row in lines(evaluation / "trial-packets.jsonl")}
    original = json.loads((base / "heldout-results/summary.json").read_text())
    audit_paths = sorted(base.glob("cross-model-audit/auditor-*.json"))
    audit_paths += sorted(base.glob("extended-blind-audit/auditor-*.json"))
    audit_paths += sorted(base.glob("paired-difference-audit/auditor-*.json"))
    judgments = defaultdict(list)
    files = {}
    for path in audit_paths:
        files[str(path.relative_to(base))] = hashlib.sha256(path.read_bytes()).hexdigest()
        for record in json.loads(path.read_text()):
            identity = record["packet_sha256"]
            packet = packets[identity]
            checked = validate_semantic_assessment(
                {"requirements": record["requirements"]},
                packet["gold_requirements"], packet["evidence_items"],
            )
            if checked["status"] != "valid" or checked["all_supported"] != record["all_supported"]:
                raise ValueError(f"Invalid cross-model audit: {path.name}: {identity}")
            judgments[identity].append(checked)
    consolidated, internal_disagreements, model_disagreements = {}, [], []
    for identity, checks in judgments.items():
        signatures = {tuple((r["id"], r["status"]) for r in c["requirements"]) for c in checks}
        if len(signatures) != 1:
            internal_disagreements.append(identity)
            continue
        consolidated[identity] = checks[0]
        model = assessments[identity]["semantic"]
        if model["status"] == "valid":
            old = {r["id"]: r["status"] for r in model["requirements"]}
            new = {r["id"]: r["status"] for r in checks[0]["requirements"]}
            if old != new:
                model_disagreements.append({"packet_sha256": identity, "frozen_model": old,
                                            "cross_model_audit": new})

    def semantic(identity: str, prior: dict, replace_valid: bool) -> dict:
        if identity not in consolidated or (prior["sufficient"] is not None and not replace_valid):
            return prior
        item = consolidated[identity]
        return {"sufficient": item["all_supported"], "coverage": item["semantic_coverage"],
                "status": "cross_model_audit", "reason": None}

    def quality(rows: list[dict]) -> dict:
        arms = {}
        by_question = defaultdict(lambda: defaultdict(list))
        for row in rows:
            by_question[row["question_id"]][row["arm"]].append(row["delivered_sufficient"])
        for arm in ("baseline", "review"):
            selected = [row for row in rows if row["arm"] == arm]
            values = [row["delivered_sufficient"] for row in selected]
            counts = Counter(values)
            arms[arm] = {"episodes": len(values), "sufficient": counts[True],
                         "insufficient": counts[False], "unknown": counts[None],
                         "rate": mean(values) if counts[None] == 0 else None}
        differences = []
        for values in by_question.values():
            if any(value is None for arm in values.values() for value in arm):
                continue
            differences.append(mean(values["review"]) - mean(values["baseline"]))
        return {"arms": arms, "question_count": len(by_question),
                "complete_question_pairs": len(differences),
                "paired_delta": mean(differences) if len(differences) == len(by_question) else None}

    modes = {}
    for name, replace_valid in (("fill_unknown_only", False), ("apply_all_audited_judgments", True)):
        rows = copy.deepcopy(original["case_audit"])
        for row in rows:
            mapping = mappings[row["trial_id"]]
            row["semantic"] = semantic(mapping["final_packet"], row["semantic"], replace_valid)
            row["delivered_sufficient"] = False if row["delivery_error"] else row["semantic"]["sufficient"]
            if mapping["first_packet"]:
                row["first_semantic"] = semantic(mapping["first_packet"], row["first_semantic"], replace_valid)
        rescues = [row["trial_id"] for row in rows if row["repairs"]
                   and row["first_semantic"] and row["first_semantic"]["sufficient"] is False
                   and row["delivered_sufficient"] is True
                   and row["first_to_final_evidence_changed"] is True]
        modes[name] = {"overall": quality(rows),
                       "families": {family: quality([r for r in rows if r["family"] == family])
                                    for family in ("micron", "spacex")},
                       "changed_evidence_rescues": rescues}
    result = {"schema_version": "knowhere-cross-model-sensitivity/1",
              "scope": "Posthoc, non-human cross-model evidence audit. Primary frozen automated scores remain unchanged. Filling unknown scores and replacing audited judgments are separate sensitivity analyses, not a new held-out replication or proof of generalization.",
              "auditor_files_sha256": files, "auditor_records": sum(map(len, judgments.values())),
              "unique_audited_packets": len(judgments),
              "invalid_automated_packets": sum(r["semantic"]["status"] != "valid" for r in assessments.values()),
              "unresolved_invalid_packets": [identity for identity, r in assessments.items()
                                              if r["semantic"]["status"] != "valid" and identity not in consolidated],
              "inter_auditor_disagreements": internal_disagreements,
              "model_audit_disagreements": model_disagreements, "sensitivity_modes": modes}
    (base / "audit-sensitivity.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    args = parser.parse_args()
    output = run(args.base)
    print(json.dumps({"audited_packets": output["unique_audited_packets"],
                      "unresolved_invalid": len(output["unresolved_invalid_packets"]),
                      "model_disagreements": len(output["model_audit_disagreements"]),
                      "modes": output["sensitivity_modes"]}))
