Review final-visible evidence before accepting agent completion, allow one bounded corrective retrieval, and expose cited coverage and honest failure states. Preserve existing behavior by default and share episode budgets.

Add contract coverage, adversarial runtime tests, and a reproducible paired experiment with an explicit semantic negative control.

## Summary

- Add opt-in `review_evidence: true` to v1/v2 retrieval queries. A separate reviewer evaluates the original question against the exact scoped, revision-pinned, composed text/table evidence returned to the caller.
- Expose an optional `evidence_review` response with `sufficient`, `insufficient`, or `unverified` status, requirement coverage, exact quotations, source provenance, usage completeness, and a final-evidence fingerprint. `answer_text` remains empty.
- Support both OpenAI-compatible and Cursor exploration harnesses. Allow at most two reviewer calls and one corrective continuation within the original episode budget; preserve the original query and first-review requirements. Handle cancellation, concurrent callbacks, final-packet changes, and abnormal stops without claiming successful verification. A reviewed tool timeout terminates the episode immediately, preserves whether the tool or episode deadline expired, and cannot lead to another model turn or an accepted finish.
- Keep review disabled by default. Separate reviewed cache entries and avoid caching unverified assessments. Classic/small-corpus routes and selected visual evidence report `unverified` when review is requested.
- API/shared retrieval behavior and CI coverage change; worker behavior, deployment topology, queues, database schema, and object storage remain unchanged.
- Related task: distinguish an explorer's decision to stop from evidence sufficiency, expose missing requirements, and permit a bounded corrective retrieval.

Example request body for the existing v1/v2 retrieval query endpoint:

```json
{
  "namespace": "default",
  "query": "Compare the standard and enterprise plans' prices and storage limits.",
  "use_agentic": true,
  "review_evidence": true
}
```

`sufficient` requires all reviewer-derived requirements to be supported by exact quotations from known evidence IDs. `insufficient` means the selected evidence has gaps or unresolved conflicts; it does not establish that the corpus has no answer. `unverified` covers unavailable or invalid review, exhausted budgets, unsupported evidence, or changes to the final evidence packet. Each corrective review must preserve the first review's requirement IDs and text. Executor reasoning, finish notes, and candidate summaries are excluded from reviewer inputs.

## Verification

GitHub Actions validation completed with Python 3.11:

- **131** shared agent-explore/review tests.
- **488** API tests, including the real PostgreSQL scope/filter contract.
- **342** worker contract tests.
- **961 tests total**; lint, production typecheck, CodeQL, and secret scan passed. CodeQL reports no new alerts in the changed code.
- **84 controlled episodes** (14 cases × 3 repeats × 2 arms), with zero failed runtime gates.

Commands run in CI:

```bash
uv sync --locked --all-packages --all-groups
uv run python apps/api/scripts/ensure_test_environment.py --install
make lint
make typecheck
uv run pytest packages/shared-python/shared/tests/test_agent_explore*.py packages/shared-python/shared/tests/test_evidence_review_projection.py -q
uv run python scripts/experiment_evidence_review.py --repeats 3 --output evidence-review-results.json
uv run pytest apps/api/tests -q
uv run pytest apps/worker/tests/contract -q
```

Additional local checks with Python 3.12:

```bash
.venv/bin/python -m pytest packages/shared-python/shared/tests/test_agent_explore*.py packages/shared-python/shared/tests/test_evidence_review_projection.py -q
.venv/bin/python -m pytest -c apps/api/pytest.ini apps/api/tests/contract/test_evidence_review_contract.py -q -k 'not seeded'
.venv/bin/ruff check apps/api packages/shared-python/shared apps/worker scripts/experiment_evidence_review.py
.venv/bin/pyright --project pyproject.toml apps/api/app apps/api/main.py apps/worker/app apps/worker/worker.py packages/shared-python/shared
git diff --check
```

The local shared suite passed 131 tests and the local API subset passed 7. The seeded database test was deferred locally because PostgreSQL was unavailable, then passed in the complete CI API suite. Automated API contracts cover v1/v2 forwarding, default-off behavior, scope/filter enforcement, cache isolation, and final-packet invalidation. Additional regressions cover early tool transport timeouts, episode deadline exhaustion, and unchanged exception propagation when review is disabled. Cancellation assertions remain bounded and verify that tasks are cancelled. No manual deployed-API, worker, browser, or live Cursor smoke checks were performed.

The paired experiment uses scripted provider/tool responses through production harness, review, composition, and finalization code. Cases include complete evidence, missing query dimensions or comparison sides, missing tables, conflicting sources, outdated evidence, an unanswerable corpus, an empty pool, reviewer failures, malformed output, budget exhaustion, and a still-incomplete correction. Both arms start with the same corpus, query, explorer behavior, and episode limits; only the enabled arm can perform the bounded correction. Its engineered coverage change (36.1% → 72.2%) is **not a measured real-model improvement**. The evaluator detects an intentionally wrong, schema-valid reviewer assessment, demonstrating that exact citations and schema checks do not prove semantic correctness.

Additional real-model evaluation completed on 2026-10-10 against this feature revision, using the literal requested and returned model `deepseek-flash`. A frozen inventory separated 10 development questions from 50 held-out questions across two document families, including 42 answerable and 8 unanswerable questions. All 300 held-out episodes ran through production retrieval tools and public evidence projection: three repetitions per question, both arms, alternating arm order, identical known-document scope, revision-pinned corpus and initial 15-step/180-second limits. The corpus contains all derived text from four checked-in documents, deterministically sliced into 765 chunks. Each of seven workers used its own PostgreSQL WASM database. Application response caching was bypassed; index caches could warm, and measured provider prefix caching remained enabled. This is a retrieval-core text experiment, not a native-database throughput or deployed-service benchmark.

| Measured outcome | Review disabled | Review enabled |
|---|---:|---:|
| Scheduled episodes / request failures | 150 / 0 | 150 / 0 |
| Frozen blind judge: confirmed sufficient | 121 | 118 |
| Frozen blind judge: unknown | 9 | 10 |
| Posthoc cross-model sensitivity: sufficient | 124/150 | 124/150 |
| Exact gold-span coverage, question macro-average | 81.33% | 81.33% |
| Actual provider tokens | 7,511,956 | 8,245,616 |
| Estimated retrieval cost, USD | 0.44144 | 0.52630 |
| Median / p95 elapsed time, seconds | 6.135 / 28.086 | 9.320 / 27.300 |

The primary semantic judge sees only the query, frozen requirements and caller-visible evidence, with arm and production verdict hidden. Its invalid assessments remain unknown: the paired sufficiency difference is bounded by -8.00 to +4.67 percentage points. A separate blind cross-model audit covered 42 packets, including the fixed preselected subset, every invalid assessment, claimed rescues and both directions of nonzero fully scored paired differences. Its sensitivity result is 124/150 sufficient episodes in each arm; it does not overwrite the primary model scores and is not human ground truth. Repetitions are averaged within questions. With only two document families, no population significance claim is made.

There is no observed net sufficiency gain in that sensitivity analysis. Tokens increased 9.77%, estimated retrieval cost 19.22%, and median latency 51.92%. Review made 66 sufficient claims, all independently supported in this sample, and returned `unverified` in 84/150 episodes: 48 exact-quotation validation failures, 5 explanations exceeding the 400-character limit, 27 episodes exhausting exploration before review, and 4 exhausting bounded correction without another valid review. Offline replay found no input/projection fingerprint mismatch and no reviewer output truncation. Most invalid quotations changed whitespace, but two quotations omitted table columns; these were not retroactively accepted. Two changed-evidence rescues were offset by two insufficient results on a different question. These results support retaining the opt-in default and improving citation reliability before claiming aggregate quality gains.

All three repetitions of the explicit semantic negative control passed: pilot approval must not establish production approval, and a throughput level must not establish percentage growth, while the stated retention period remains supported. Passing this control is not proof of universal semantic reliability. The 206 offline judging calls used 876,366 tokens and cost approximately USD 0.114, reported separately from retrieval. Usage was complete; monetary amounts use the 2026-10-10 off-peak list rates of USD 0.003 per million cached input tokens, 0.15 per million uncached input tokens and 0.6 per million output tokens. They are estimates rather than invoices and exclude development/calibration.

The measured benchmark initially used an incorrect equality guard that rejected legitimate correction-budget reductions in four episodes. Independent trace audits found zero actual reviewed budget violations. Those four original false gates and their unverified outcomes remain recorded; only unstarted IDs were resumed, with the exact frozen code and no outcome replacement. The benchmark-only guard was repaired after all measurements. An earlier development database-launcher timeout and interrupted episode are also retained and excluded from held-out estimates. Production feature code was not tuned on these observed outcomes.

Intentionally not tested: a deployed end-to-end service, real PDF/image parsing, document discovery without known scope, live Cursor execution, API authentication/billing, workers, or native PostgreSQL concurrency in the live benchmark. The broader shared suite also has an existing failure in `test_recall_blank_query_is_rejected`, reproduced on the unchanged upstream baseline and outside this change.

## Deployment Notes

- **Environment variables:** none added or changed. The reviewer reuses existing request-scoped text-provider configuration. Direct OpenAI-compatible providers and BYOK are supported; pooled-only/mock reviewer backends report `unverified`.
- **Database, queues, and storage:** no migrations, queue changes, object-storage changes, new services, or API/worker release-order requirements.
- **Compatibility:** `review_evidence` defaults to `false`, adding no reviewer calls. The API response gains an optional nullable `evidence_review` field. Enabling review adds bounded model usage and latency, reported separately and within the shared episode budget.
- **Caching and rollback:** reviewed requests use a separate versioned cache key; unverified results are not cached. Disable the request flag to stop review. Reverting the release requires no data migration or storage rollback.
- **Runtime limits:** text/table review only; at most two reviewer calls and one correction. Each review has a 30-second ceiling, further bounded by the remaining episode time and including evidence loading. Serialized input is capped at 64 KiB and output at 1,024 tokens; oversized evidence is unverified rather than silently truncated. After the first insufficient review, at most four remaining steps are available, including the second review, without extending the original episode budget. Existing pick-phase accounting is unchanged. Cancellation cannot immediately terminate an already-running synchronous transport/storage operation; late results cannot change the finalized reviewed pool. Missing token usage remains explicitly unknown.

## Checklist

- [x] Tests were added or updated when behavior changed.
- [x] Public docs, examples, or OpenAPI contracts were updated when needed.
- [x] Database migrations are idempotent and safe to deploy. **Not applicable: this PR adds no migrations.**
- [x] Logs, errors, and validation paths avoid leaking secrets or user data. Reviewer inputs use request-scoped evidence; returned citations and traces follow the existing authorized retrieval path.
- [x] The pull request description explains any breaking or user-visible change.
