# Mac confirmation release verification

Measurement and primary-agent interpretation are complete: 144 original episodes, 72 per arm, 152 unique arm-blind packets plus three passed fresh controls. Two invalid span-range judgments and seven connection failures remain in the data. Both arms confirmed 52/72 sufficient deliveries; bounds include zero, so no net benefit is confirmed. Complete retrieval costs are unknown.

The measured revision is `6c12e6971cffe900aec98805a78e35d55aca9239`, not the subsequent documentation commits. The unchanged production feature is `d4d32ad74091b4040e1a1e8d7dae10f6a5b222c1`. No experimental code, gold or runtime was promoted to production.

## Immutable archive set

| Archive | Members |
|---|---:|
| mac-native-tokenizer.tar.gz | 4 |
| mac-restoration-records.tar.gz | 28 |
| mac-development-records.tar.gz | 34 |
| mac-validation-records.tar.gz | 26 |
| mac-heldout-records.tar.gz | 31 |
| mac-release-evidence.tar.gz | 31 |
| Total | 154 |

All six archive sizes/hashes and every regular member's exact path/size/hash were verified against separate manifests. Paths are unique, safe and relative, with no links/devices. Private credentials/PEM material, database files, dependency checkouts and JSON/JSONL private-reasoning/header fields were checked and absent. The four pre-existing Mac archives were not overwritten. The exact native tokenizer is an explicit licensed binary component, not a dependency checkout.

Heldout archive SHA-256: `2d41a923707a48e5a0b66115f0af4b72de61a6b16a3941874fee15ba62507f5b`.

Supplemental archive SHA-256: `a0a031ccbf35f2761d8bb97c00aa95964549fd561340f78e180a195ec7794b51`.

The supplement preserves the original archive/report helper failures, original source hash and captured traceback, offline repair and 36-test evidence, independent accounting/draft and tools, deterministic audits, original scanner failures with every fingerprint classification, five-stage member verification, host-sleep/network/non-convergence observations, primary report review, first normal-push observation, and both final PR responses. The accounting draft is retained as a draft: four public correction counters are not all corrective activity; the final report explicitly includes two additional failed episodes entering correction.

## Scanner and non-self-referential sidecars

The unchanged scanner recursively scanned the six-archive set with depth 2, existing allowlist/config disabled by the same original flags, and redacted report output. It exited **1**, with **132 findings**. Each finding was independently verified as the exact named `runtime_source_sha256` at the protocol-recorded Git revision; zero unresolved candidates. Classification is not a green scanner result. No scanner configuration, allowlist or Git history was modified.

- `mac-release-member-verification.json`: six-archive, 154-member integrity/private-material observation.
- `mac-release-scan.json` and `mac-release-scan-classification.json`: raw scan and every individual classification after adding the supplement.
- `mac-publication-scan.json` and `mac-publication-scan-classification.json`: final scan after adding this release note and the initial sidecars; original exit/findings remain retained.

These sidecars intentionally sit outside the immutable supplement: an archive cannot contain its own final hash verification. A scanner-output file is also a dated snapshot of its inputs, not a claim that it recursively scanned itself. Final generated sidecars were separately checked for public material before staging.

## Normal publication and PR responses

Only experiment documents and evidence were staged after all original retrieval/evaluation processes exited and after inspecting worktree changes. The existing San_Check identity (`56502269+xcosmosbox@users.noreply.github.com`) normally committed/pushed the final reports and five stage archives as `2a98087da9b8a1fd1e63927d17cb5c0374c7611b` on `test/xcosmosbox/evidence-review-mac-v3`; `ls-remote` matched and the worktree was clean. This supplement/note/sidecars are carried by a subsequent ordinary documentation/evidence commit on that same branch; its final SHA is established by Git and the run-root final-delivery observation, avoiding a self-referencing commit hash in this file.

The existing project-scoped GitHub helper updated Ontos-AI/knowhere PR 457 and xcosmosbox/knowhere PR 1 with the saved self-contained, no-external-link `PR_BODY.md`. Both returned HTTP 200 on 2026-10-11 21:46 UTC; response bodies exactly match the saved final body and both heads remain the unchanged production feature. Both PRs remain open and unmerged.

Final PR body SHA-256: `b8ee0d997e16b22c1e1577263ea882d782320e71857ce7067420536474b18712`. Full response evidence (`pr-update-final.json`) and its verification are in the supplemental archive; no credential or request header was persisted.

There was no force push, main change, merge, started-ID resend, scoring retry or global power-setting change. Historical scores, unknown usage/counters, seven connection failures, two invalid assessments, original helper failures and raw scanner failure remain intact. Production CI success is separate from model quality; fork all-history Gitleaks remains failed on its separately verified historical findings. The completed continuation heartbeat is stopped after final push/remote verification; the desktop app is not closed.
