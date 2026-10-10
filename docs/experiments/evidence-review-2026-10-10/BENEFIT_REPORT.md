# Real-model benefit evaluation

The current evidence supports keeping review optional. This experiment did not
establish an aggregate evidence-sufficiency gain, while token use, estimated cost
and median latency increased. The strict reviewer correctly avoided accepting
invalid citations, but its high `unverified` rate limits its practical usefulness.

## Measured comparison

We ran all 300 scheduled episodes: 50 held-out questions, three repetitions and
two arms. Both arms used the actual `deepseek-flash` API, production retrieval
tools, the same published text corpus and document scope, and the original
15-step/180-second initial budget. All requests completed; provider token and
cache usage are complete. Only `review_evidence` differed between arms.

| Measure | Review disabled | Review enabled |
|---|---:|---:|
| Scheduled episodes | 150 | 150 |
| Primary blind judge: confirmed sufficient | 121 | 118 |
| Primary blind judge: unknown | 9 | 10 |
| Posthoc cross-model sensitivity: sufficient | 124/150 | 124/150 |
| Exact gold-span coverage, question macro-average | 81.33% | 81.33% |
| Actual provider tokens | 7,511,956 | 8,245,616 |
| Estimated retrieval cost, USD | 0.44144 | 0.52630 |
| Median elapsed time | 6.135 s | 9.320 s |
| Mean elapsed time | 10.639 s | 13.196 s |
| p95 elapsed time | 28.086 s | 27.300 s |

The primary analysis preserves invalid semantic assessments as unknown. Its
paired sufficiency difference is bounded by **-8.00 to +4.67 percentage points**;
the lower confirmed count is not evidence of a three-episode regression. A
separate posthoc blind cross-model audit resolves all unknown packets and yields
124/150 sufficient episodes in each arm (82.67%; 124/126 among answerable
episodes). This sensitivity analysis does not replace the frozen model scores
and is not human ground truth. Both document families also have zero net gain
under this analysis. No p-value or population confidence interval is claimed.

Tokens increased **9.77%**, estimated retrieval cost **19.22%**, and median
elapsed time **51.92%**. These are measurements on this shared host and workload,
not native PostgreSQL throughput or production-service latency guarantees.
The 206 separate offline judging calls used 876,366 tokens and cost approximately
USD 0.114 at the dated list rates; they are excluded from retrieval overhead.
All monetary amounts are estimates from actual usage, not invoices, and exclude
calibration/development requests. Rates were USD 0.003 per million cached input
tokens, 0.15 per million uncached input tokens and 0.6 per million output tokens
on Saturday, 2026-10-10, using the official off-peak schedule.

## What the completion judgment actually did

Review returned `sufficient` in 66/150 episodes. All 66 claims were independently
scored as supported, giving zero observed false-sufficient claims in this sample.
The other **84/150 (56%)** were `unverified`; none returned `insufficient` as its
final public status. A zero false-insufficient count therefore does not imply
useful coverage of negative decisions.

Offline replay of every actual reviewer response identified:

- **48 episodes** rejected for non-exact quotations. Across their citations,
  116 mismatches involved whitespace, one involved a hyphenated line wrap, and
  two omitted an intervening table column. Citation counts are not episode counts.
- **5 episodes** rejected because explanations exceeded the 400-character limit.
  Actual lengths were 442–875; the prompt requested a short explanation without
  explicitly stating that limit.
- **27 episodes** exhausted exploration steps before a reviewer could run.
- **4 episodes** exhausted the bounded correction allowance before a second valid
  review could accept the final packet.

All 123 reviewer calls ended normally, with 176–911 output tokens; none hit the
1,024-token output cap. Reconstructed input prompts matched their saved snapshots
and hashes, and final-packet fingerprints matched. No projection defect was found.
The raw invalid responses remain invalid in the primary results; diagnostic
whitespace comparisons did not retroactively accept them.

Two repeats of the five-step-algorithm question gained sufficient evidence after
correction, with changed final packets. Their public review status correctly
remained `unverified` because a second review had not completed. In the paired
comparison, two other repeats of a different question lacked sufficient evidence
in the enabled arm. Those differences cancel in the aggregate; they do not prove
a reproducible per-question treatment effect from three repetitions.

## Evaluation integrity and limits

The inventory and execution protocol were committed before held-out requests.
The 60-question inventory has ten development questions and fifty held-out
questions; the held-out portion contains 42 answerable and eight unanswerable
questions from two document families. Repetitions are averaged within questions.
The corpus uses all derived page text, sliced deterministically into 765 chunks,
without using gold labels to choose source content. Revision pins and the actual
index digest match across all seven isolated workers.

The semantic judge receives the original query, frozen requirements and only
caller-visible evidence, with arm and production verdict hidden. Three repeated
runs of the explicit negative control correctly distinguish pilot approval from
production approval, log retention from unrelated facts, and a throughput level
from year-over-year percentage growth. This checks that control, not universal
semantic reliability. The independent prompt still uses the same DeepSeek model
family, so correlated errors remain possible.

The fixed cross-model audit covers sixteen preselected episodes, deduplicated to
ten packets. Additional posthoc audits cover every invalid independent assessment,
both claimed correction rescues, and both directions of every fully scored
nonzero paired sufficiency difference. Auditors receive no arm or prior verdict;
their citations are mechanically validated against visible evidence. Audit
selection, judgments, disagreements and sensitivity calculations are saved
separately. These are agent audits, not human adjudication.

Four episodes triggered an erroneous benchmark equality gate because production
legitimately lowered the correction step cap: 15 to 10, 8, 8 and 11. Independent
trace audits verified exact charged-step boundaries and **zero real reviewed
budget violations**. Each raw `false` gate and `unverified` verdict is preserved.
The identical frozen runner resumed only unstarted IDs; no completed episode was
replaced. After all model calls and scores completed, the benchmark guard was
fixed with regression tests. The original measured protocol and a new, explicitly
unexecuted reproduction protocol remain separate.

An earlier development launcher defect mishandled PostgreSQL SSL negotiation and
caused connection-close delays. Its timeout and interrupted episode are retained
as development failures, never substituted into or hidden from the held-out data.
The fixed launcher passed the remaining eighteen development episodes.

This tests the retrieval core on PostgreSQL WASM with known document scopes and
text derived from checked-in documents. It does not test document discovery,
PDF/image interpretation, native database concurrency, API authentication,
billing, workers or production traffic. Application response caching is bypassed;
local index caches can warm, provider prefix caching remains enabled and measured,
and Redis readiness notifications use their existing fail-open path. Baseline
forced finishes can use a sixteenth charged step; this legacy behavior is retained
and disclosed rather than silently giving both arms new hard limits.

## Next experiment

Prioritize reliable source-anchored citation production and explicit explanation
length instructions. Keep exact source provenance and rejection of deleted table
columns; broad fuzzy matching would hide genuine errors. Then investigate reserving
review/correction steps within the same total budget, measuring any loss of initial
exploration. Test those changes on newly frozen document families and questions;
the present held-out set has now been observed and must not become a fresh
confirmation set after tuning. This report does not justify enabling review by
default or claiming improved final-answer accuracy.

## Artifacts and verification

`heldout-results/summary.json` and `heldout-results/RESULTS.md` are the untouched
primary automated aggregates. `audit-sensitivity.json` is the separate posthoc
analysis. `review-validity-diagnostic.json`, `runtime-budget-audit.json` and
`benchmark-gate-fix.json` explain failures and the later guard repair. Compressed
raw records have per-file SHA-256 manifests; `REPRODUCE.md` gives extraction,
offline aggregation and new-run commands. No provider credential is included.

The production feature remains at
`f68cee2d2793dc4d6fa5cb9281f3d6d357826b1b`. Its upstream CodeQL check is successful
with zero annotations, and all six CI checks pass. The existing CI suite passed
961 tests. Experiment implementation and records are isolated from that feature
revision; this evaluation adds no production migration or deployment requirement.
