## Summary

Task: add an opt-in completion boundary that checks whether the caller-visible evidence supports the original retrieval query, with at most one corrective retrieval. No related issue was supplied.

Set `review_evidence: true` on an agentic v1/v2 retrieval request. The default stays false and performs no reviewer calls. The endpoint still returns evidence, not an answer; `answer_text` stays empty. Public states are `sufficient`, `insufficient`, and `unverified`. Unknown review validity is never promoted to sufficient or cached.

The reviewer sees only the original query and final text/table evidence after permission, document-scope, revision and response filtering. It does not see explorer reasoning, finish notes or candidate summaries. Deterministic checks enforce schema, stable facet requirements on the second review, exact source citations and a final evidence fingerprint. Two reviews and one correction share the existing production episode budget.

This continuation fixes observed citation-format and reason-length failures. Each evidence item now exposes an ordered lossless source-span partition internally; the model chooses an inclusive contiguous range, and the service reconstructs the exact original quote. Python Unicode code points, CRLF, tabs, every table column and punctuation are preserved. Public citations remain `{evidence_id, quote}`; legacy quote responses remain exact-only, without fuzzy matching or normalization. The prompt states the existing 400-character reason limit. Reviewed cache keys use a v2 salt; ordinary cache keys are unchanged.

A fresh-context model code review found a real server-side quote-amplification defect. A local reproduction expanded a 14,373-byte assessment into 7,684,608 canonical quotation bytes. The fix checks UTF-8 size before joining ranges and caps all reconstructed citation text across every facet at 16,384 bytes. Oversized reports fail closed without shortening or semantically repairing citations. A separate follow-up established no actionable defect in this guard, but was static same-family model review, not human review or CodeQL.

## Verification

The final production head is `d4d32ad74091b4040e1a1e8d7dae10f6a5b222c1`. Upstream checks at this exact head completed successfully: Test, Lint, Typecheck, Analyze, CodeQL and Gitleaks. CodeQL reports no new alerts in the changed code.

The fork's Test, Lint, Typecheck, Analyze and CodeQL checks also succeeded. Its Gitleaks current-tree scan passed, but the all-refs Git-history scan failed on 66 generic-api-key findings in three historical experiment protocols on commits `2ccb9e80` and `69166a4d`. Every reported value was verified to be a `runtime_source_sha256` field matching the corresponding source file at that same commit. Neither historical commit is an ancestor of the production feature head or synced main. The failed remote check remains failed; no scanner configuration, allowlist or history was changed to make it green.

Local macOS arm64 checks:

- Shared evidence-review/harness/projection tests: 161 passed.
- Worker contract tests: 342 passed.
- API suite, run sequentially: 487 passed and one environment-dependent DNS failure. The same private-redirect test fails at the original feature head because `example.com` cannot resolve before the mocked HTTP call. No security check or assertion was weakened. Earlier API/worker concurrency caused two additional shared-temp-storage failures; both passed when isolated.
- Controlled finish/review experiment: 14 cases × 3 repeats × 2 arms = 84 scripted episodes, all runtime gates passed after adapting its source-only input audit to lossless spans. Verdicts and simulated usage remain predetermined; the deliberately false semantic claim control is not live model evidence.
- Production Makefile typecheck scope: zero errors. Ruff checks pass. A broader no-argument typecheck includes 14 test-file type errors outside that production scope and is not reported as green.
- New benchmark tooling, frozen inventory, independent scorer and scope accounting: 136 tests passed; summary self-test passed. Historical replay validated five archives, 146 entries and 398 source fingerprints and restored all 300 original episodes without changing their scores.

Commands (repository root):

```text
python -m pytest packages/shared-python/shared/tests/test_agent_explore*.py packages/shared-python/shared/tests/test_evidence_review_projection.py -q
python -m pytest apps/api/tests -q
python -m pytest apps/worker/tests/contract -q
python scripts/experiment_evidence_review.py --repeats 3 --output evidence-review-results.json
make lint
make typecheck
```

Do not run API and worker contract suites concurrently: they share a temporary object-storage root. On Mac, the tests additionally require a native PostgreSQL executable with matching pg_trgm and uuid-ossp extensions; those are isolated test dependencies, not changes to the PGlite experiment backend.

Existing real-model evidence remains negative for overall retrieval benefit. The original 300 episodes used 50 held-out questions × 3 repeats × 2 arms. Original arm-blinded confirmed sufficiency was 121/150 baseline versus 118/150 review, with 9/10 unknowns. Separate posthoc cross-model sensitivity analysis found 124/150 in each arm, no net gain. Review returned `unverified` in 84/150 episodes: 48 non-exact citations, 5 overlong reasons, 27 exploration step exhaustion and 4 incomplete second reviews. All 123 reviewer calls stopped normally at 176–911 output tokens; no observed 1,024-token truncation explains those failures.

That historical workload used 7,511,956 versus 8,245,616 provider tokens, dated estimated retrieval costs of USD 0.44144 versus 0.52630, and median latency 6.135 versus 9.320 seconds. These are the earlier workload/host observations, not Mac production estimates. Offline semantic judgment was separate, same-family automated evaluation; unknowns were not set to zero. Zero false-sufficient among 66 valid historical sufficient claims is sample-limited and coexists with a 56% unverified rate.

New RFC experiments use separate frozen protocols, real DeepSeek Flash calls, thinking/max and provider-maximum output with no local step, time, input/output-byte or financial ceilings. The scope-feedback factor is shared by both arms and is not gold truth. The completed 12-episode scoped development run has no unknown blind scores: both arms are 5/6 sufficient; review returns 5 sufficient and one valid insufficient, no unverified. All three real semantic negative controls passed. An offline audit verified all 7 reviewer outputs, exact final public fingerprints and full-read receipts. Development samples and environment smoke do not demonstrate held-out benefit.

The formal confirmation has now completed all 144 frozen episodes, 72 per arm, at revision `6c12e6971cffe900aec98805a78e35d55aca9239`. This is a custom project-built question inventory, not an official benchmark: only the full RFC source texts are official. There are 24 held-out JSON/QUIC questions, three repeats, 20 answerable and four partially unanswerable questions, and only two document families. Experimental holdout does not establish absence from pretraining. No prompts, gold, sources, model settings or criteria changed during measurement; no failed identity or invalid score was resent.

| Confirmatory metric | Baseline | Review |
|---|---:|---:|
| Confirmed sufficient delivery | 52/72 | 52/72 |
| Delivery failures | 2 | 5 |
| Unknown semantic scores, including failed deliveries | 2 | 7 |
| Unknown delivery sufficiency | 0 | 2 |
| Conservative delivery sufficiency bounds | 72.22% | 72.22–75.00% |
| Answerable confirmed delivery | 52/60 | 52/60 |
| Semantic requirement-coverage bounds | 79.17–81.94% | 76.39–86.11% |
| Literal gold-span recall | 79.17% | 79.17% |

Repeats are averaged within questions and arms are paired. The conservative sufficient-delivery difference is 0 to +2.78 percentage points, containing zero; semantic-coverage difference is −5.56 to +6.94 points. These are unknown-state arithmetic bounds, not confidence intervals. The frozen sample does not confirm a net sufficiency gain. Failed delivery is not proof of latent semantic insufficiency; unknown scores are neither zero nor passes. JSON confirms 25/36 versus 26/36; QUIC 27/36 versus 26/36. Literal matching is not semantic truth.

Review publicly returned 51 sufficient, four insufficient and 12 unverified results, with five public responses missing: valid final reviews 55/72. False-sufficient is 0/49 independently scored sufficient claims, with two additional claims unknown; false-insufficient is 0/4 scored insufficient claims. The original summary's alternative zero among 52 independently sufficient deliveries uses a different denominator. Four nonmissing public correction counters yielded zero rescues among four independently scored initially insufficient first finishes. Two additional failed episodes captured an insufficient reviewer output and subsequent correction exploration; their public counters and eligible first-score mappings are missing. Four must not be described as all corrective activity. All 61 captured reviewer calls, including two in failed episodes, remain in usage accounting.

| Retrieval role | Calls | Observed tokens subtotal | Cached / uncached input | Completion, including thinking | Known dated USD subtotal | Calls missing usage |
|---|---:|---:|---:|---:|---:|---:|
| Baseline explorer | 539 | 16,328,346 | 2,317,440 / 3,126,692 | 10,884,214 | 7.006484520 | 2 |
| Review total | 705 | 24,279,001 | 4,242,176 / 5,709,284 | 14,327,541 | 9.465643728 | 5 |
| Review explorer | 644 | 23,232,383 | 4,117,632 / 5,038,033 | 14,076,718 | 9.214088646 | 5 |
| Review reviewer | 61 | 1,046,618 | 124,544 / 671,251 | 250,823 | 0.251555082 | 0 |

Complete retrieval usage and cost remain unknown in both arms. Known subtotals are not total costs or bills; no complete cost-overhead percentage or cost per additional sufficient delivery is claimed. Recorded calls with known usage start/end on UTC 2026-10-11, using that Sunday's versioned per-million cached/uncached/output USD rates 0.003/0.15/0.6. Reasoning metadata is a subset of completion, not an additional charge. Seven unreturned requests and server-side billing remain unknown; role completeness across failed episodes is not inferred from captured reviewer calls.

Recorded monotonic mean/p50/p95 seconds are baseline 716.907/279.651/2799.529 and review 966.764/294.459/3971.227. Independent UTC elapsed is 729.685/279.652/2799.532 and 992.319/294.459/3971.231. Both retain all 72 episodes. The host had a 922-second clamshell sleep; three overlapping failures have roughly 920 seconds more UTC than recorded duration. Sleep overlap is not proof of sole cause, and this is not a clean production-latency comparison. The user also reported switching networks near later failures; exact timing and sole attribution were not verified. No global power settings changed.

The long `rfc-held-024:2:review` lasted about 3 hours 20 minutes and 76 calls, fully read all 183 scoped units, then continued repetitive search/pick activity for about 75 minutes after a scope-exhaustion hint before connection failure. This is observed system-level non-convergence/non-delivery, separate from the possible transport interruption. The exhaustion hint is prompt-only, not an enforced stop. No retrospective three-hour timeout was imposed, and finite non-convergence does not prove it could never finish. Thinking, model and reviewer causality cannot be isolated; long baseline episodes also occurred. Another review failure lasted 16.6 minutes and is recorded separately. Stops remain baseline finished/no_tool_call/no_response 56/14/2 and review 55/12/5; fake tool text was not repaired and no provider length finish was observed.

Arm-blind scoring completed 152 deduplicated packets plus three fresh real semantic negative controls, 155 calls. All three controls rejected unsupported production-approval and growth assertions while recognizing supported retention. Two invalid source-span-range assessments remain unknown, without retries. Evaluator usage is complete: 2,148,709 tokens, 614,396 cached input, 1,399,569 uncached input and 134,744 completion tokens; separate list estimate USD 0.292624938, never retrieval overhead. This is a fresh blind prompt with fixed gold but the same DeepSeek model family, not human or independent-family truth; controls do not establish universal reliability.

Independent offline arithmetic verified full denominators, unique starts, hashes, blind mappings, claims/corrections, literal ownership, actual provider parameters/cache/dates and both clocks. A separate deterministic source audit checked all 144 records, 402 runtime fingerprints and 61 valid reviewer schemas without errors. Source validation is not semantic truth. Historical/development/confirmation results remain separate; multi-factor changes versus history cannot establish thinking-only benefit. Explorer reconstructs a fresh system/user prompt per action rather than carrying a native assistant/tool/private-reasoning conversation. Only two public document families, shared judge family, no full human adjudication, and no production-traffic sample prevent population-wide benefit claims.

Five immutable Mac stage archives have 123 individually verified members, including all formal records. The unchanged recursive scanner exits 1 on 132 candidates, each verified as the exact historical protocol source SHA-256 at its recorded revision; no unresolved finding was found, but the raw scan remains failed. The original archive helper itself failed on quoted PEM-detector source text, and the dependent report helper failed; both failures are retained. A post-run offline material-aware guard repair with no path exemptions passed 18 guard and 18 accounting tests. The initial unrelated libpq/pytest plugin startup failure remains separately documented. No model work was restarted. Final supplemental evidence preserves audits, original scans/classifications, accounting, helper failures/repair, environmental observations and final PR response metadata, with non-self-referential archive verification sidecars. Documentation and archival commits only affect the existing experiment branch; measured and production revisions remain distinct.

## Deployment Notes

No database migration, new queue, storage-format change or new production environment variable. Existing production limits remain two reviews, one correction, a shared 15-step/180-second episode, a reviewer ceiling of 30 seconds, 1,024 output tokens and 64 KiB serialized input. The 16,384-byte assessment and canonical quotation bounds close the new locator's response amplification. Experimental resource overrides are process-local and are not production defaults.

Review remains default-off and can be disabled per request. Reviewer timeout, malformed output, unsupported page/image evidence, classic/small-corpus routing or changed final evidence returns `unverified`; it is not evidence of sufficiency or insufficiency. Cursor integration has regression coverage, but no new live Cursor validation. Experiments call the retrieval core/public projection and bypass HTTP auth, billing, upload/parser workers and application response cache; they are not full online-service end-to-end acceptance.

## Checklist

- [x] Default-off behavior and ordinary cache compatibility preserved.
- [x] Source, revision, frozen-facet and final-fingerprint checks retained.
- [x] Citation amplification reproduced and repaired without fuzzy matching.
- [x] Relevant regressions, controlled run and production lint/type checks executed; actual failures documented.
- [x] Historical results, new protocols, unknowns and independent review findings kept separate.
- [x] New upstream remote CI and CodeQL verified for the final feature head; fork history-scanner failure explicitly diagnosed.
- [x] New held-out confirmation, true unknowns/failures and no-confirmed-net-gain conclusion finalized; stage evidence verified and release evidence retained separately.
- [ ] Maintainer review and merge (not performed by this task).
