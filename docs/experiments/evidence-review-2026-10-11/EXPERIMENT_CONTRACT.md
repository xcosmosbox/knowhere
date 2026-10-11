# Mac continuation: frozen experiment contract

This is a new resource intervention, not a rerun or replacement of the historical 300 episodes. It tests the v2 lossless citation locator under DeepSeek Flash thinking/max with provider-maximum output and no local step, time, input-size or money ceiling. Both arms use the same intervention; only `review_evidence` differs. One correction and two reviews remain the finite workflow, not a cost-saving policy. Source, permission, schema and final-fingerprint checks remain mandatory. Production defaults remain unchanged and review remains default-off.

## Prior evidence and attribution

The old primary score was baseline 121/150 versus review 118/150, with 9/10 unknown scores. Separate posthoc sensitivity analysis produced 124/150 in both arms. Review's 84/150 `unverified` episodes comprised 48 non-exact citations, 5 reasons over 400 characters, 27 exploration step exhaustion and 4 incomplete second reviews. All 123 reviewer calls stopped normally with 176–911 output tokens: no observed 1,024-token truncation. Disabling thinking is an experimental model setting, not automatic invalidation; its causal effect is not established by those records.

The new experiment changes thinking, resources and citation prompts relative to history, so a historical difference cannot isolate any one change. The within-new-run paired difference tests enabling the revised review workflow under the new configuration. It does not establish the separate benefit of thinking or compare v1 and v2 at identical resources.

## Inventory and fixed schedule

- Sources: complete, byte-preserved RFC 2119, 8259, 7493, 9000 and 9001 from the official RFC Editor. Notices remain included. One logical full-text page-type container per document, followed by the existing deterministic 3,500-character windows with 400-character overlap. No gold-driven extraction, normalization, PDF parsing or visual interpretation.
- Development: 6 RFC 2119 questions, one repeat, two arms: 12 episodes. One question requests a deliberately absent operational measurement. These are not benefit metrics.
- Held-out: 24 questions, JSON and QUIC families with 12 each, three repeats, two arms: 144 episodes. Twenty answerable and four partly unanswerable questions. The 48 fixed requirements cover normative strength, comparisons, multiple sources, text tables/columns, quantities/units, conditional rules and related-but-non-entailing facts.
- Questions, requirements, proofs and unavailable-fact notes are authored and exact-proof checked before any new-inventory model output. This is unseen within this experiment, not guaranteed unseen in model pretraining. Public normative documents and two families are not representative production data.
- Development uses one database/worker. Confirmation uses three logical shards and three concurrent workers, a separate database and durable output for each. Within-worker episodes are serial; arm order alternates. Application response cache is bypassed; index/provider prefix caches may warm and are measured.

## Independent scoring and stopping

Gold requirements remain independent of production reviewer facets. A separate arm-blinded prompt sees only query, fixed gold and caller-visible source-verified evidence. Gold proofs are evaluation standards, not returned evidence. It selects lossless source-span ranges; an independently implemented locator reconstructs canonical quotes and exact/source/schema checks validate them. A present quote is not proof of entailment. Three real semantic negative controls must pass before scoring. The judge is the same DeepSeek family, not human or independent-model truth.

Each scheduled episode and each deduplicated blind packet is called once. Natural finish, explicit failure or cancellation stops a call; no retries to get a better answer. Interrupted starts are retained as failures/unknowns, not resent. No mid-run prompt, inventory, model setting or validator changes. Frozen mismatch or policy-gate failure stops the affected worker and keeps its data; any changed experiment uses a new protocol/directory. Completion uses the full frozen denominator, never just successful results. Unknown semantic scores are not zero and not passing.

The aggregate unit is the question, averaging repeats before pairing arms. Report sufficiency and facet coverage, literal span recall separately, false claims and independently scored denominators, unverified reasons, attempted correction denominator, evidence changes/rescues, usage/cache fields, latency distributions and dated estimated costs. Retrieval and offline scoring cost are separate. Sunday 2026-10-11 UTC prices were rechecked on the official page: per million cached input USD 0.003, uncached input 0.15, output 0.6. Unknown usage/dates remain unknown; no financial limit is imposed. No p-values or population significance claims.

## Pre-confirmation verification

The historical replay recovered all 300 episodes and sensitivity results without altering old records. An arm64 build of the exact locked BlingFire v0.1.8 source restored the original 123,307-row index, with all original index checks identical. The first new thinking smoke failed because named tool choice is unsupported; that record is retained. After the explicit sole-pick-tool `auto` compatibility fix, both smoke episodes succeeded with all runtime gates, complete model/usage, baseline with no reviewer, and review `sufficient` with two exact final-source citations. This proves the Mac call chain, not benefit.

Production regression, benchmark contracts and frozen-inventory/scorer tests precede development. Held-out calls begin only after development and negative-control checks. Frozen protocol files, raw trials, start/provider journals, index verification, blinded packets, assessments, source fingerprints and failure records are archived separately from production fixes.
