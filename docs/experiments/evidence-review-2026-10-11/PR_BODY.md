## Summary

Task: add an opt-in completion boundary that checks whether the caller-visible evidence supports the original retrieval query, with at most one corrective retrieval. No related issue was supplied.

Set `review_evidence: true` on an agentic v1/v2 retrieval request. The default stays false and performs no reviewer calls. The endpoint still returns evidence, not an answer; `answer_text` stays empty. Public states are `sufficient`, `insufficient`, and `unverified`. Unknown review validity is never promoted to sufficient or cached.

The reviewer sees only the original query and final text/table evidence after permission, document-scope, revision and response filtering. It does not see explorer reasoning, finish notes or candidate summaries. Deterministic checks enforce schema, stable facet requirements on the second review, exact source citations and a final evidence fingerprint. Two reviews and one correction share the existing production episode budget.

This continuation fixes observed citation-format and reason-length failures. Each evidence item now exposes an ordered lossless source-span partition internally; the model chooses an inclusive contiguous range, and the service reconstructs the exact original quote. Python Unicode code points, CRLF, tabs, every table column and punctuation are preserved. Public citations remain `{evidence_id, quote}`; legacy quote responses remain exact-only, without fuzzy matching or normalization. The prompt states the existing 400-character reason limit. Reviewed cache keys use a v2 salt; ordinary cache keys are unchanged.

A fresh-context model code review found a real server-side quote-amplification defect. A local reproduction expanded a 14,373-byte assessment into 7,684,608 canonical quotation bytes. The fix checks UTF-8 size before joining ranges and caps all reconstructed citation text across every facet at 16,384 bytes. Oversized reports fail closed without shortening or semantically repairing citations. A separate follow-up established no actionable defect in this guard, but was static same-family model review, not human review or CodeQL.

## Verification

Local macOS arm64 checks on the revised production patch:

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

New RFC experiments use separate frozen protocols, real DeepSeek Flash calls, thinking/max and provider-maximum output with no local resource/financial ceilings. The new scope-feedback factor is shared by both arms and is not gold truth. The completed 12-episode development run has no unknown blind scores: both arms are 5/6 sufficient; review returns 5 sufficient and one valid insufficient, no unverified. All three real semantic negative controls passed. Development samples and environment smoke do not demonstrate held-out benefit. New confirmation results and new remote CI/CodeQL status are not yet claimed here.

## Deployment Notes

No database migration, new queue, storage-format change or new production environment variable. Existing production limits remain two reviews, one correction, a shared 15-step/180-second episode, a reviewer ceiling of 30 seconds, 1,024 output tokens and 64 KiB serialized input. The canonical quotation bound closes the new locator's response amplification.

Review remains default-off and can be disabled per request. Reviewer timeout, malformed output, unsupported page/image evidence, classic/small-corpus routing or changed final evidence returns `unverified`; it is not evidence of sufficiency or insufficiency. Cursor integration has regression coverage, but no new live Cursor validation. Experiments call the retrieval core/public projection and bypass HTTP auth, billing, upload/parser workers and application response cache; they are not full online-service end-to-end acceptance.

## Checklist

- [x] Default-off behavior and ordinary cache compatibility preserved.
- [x] Source, revision, frozen-facet and final-fingerprint checks retained.
- [x] Citation amplification reproduced and repaired without fuzzy matching.
- [x] Relevant regressions, controlled run and production lint/type checks executed; actual failures documented.
- [x] Historical results, new protocols, unknowns and independent review findings kept separate.
- [ ] New remote CI and CodeQL verified for the final feature head.
- [ ] New held-out confirmation and complete experiment archive finalized.
- [ ] Maintainer review and merge (not performed by this task).
