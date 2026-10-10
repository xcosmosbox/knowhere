# Evidence-review benefit evaluation

Recorded on 2026-10-10. Status: **live evaluation blocked at provider preflight**.
No real-model benefit, latency, or monetary-cost estimate has been produced.

## Verified starting point

The feature revision is `f68cee2d2793dc4d6fa5cb9281f3d6d357826b1b`.
The CI merge revision is `3422d1fe79fdc1674a128ad305467c96a206d15b`.
Upstream CI run `38016425661` passed 131 shared tests, 488 API tests, and
342 worker contract tests: 961 tests in total. Lint, production typecheck,
and secret scanning passed. CodeQL check `114107860033` completed successfully
with zero code-scanning annotations.

The fixes remove ineffective statements while preserving cancellation checks,
and terminate reviewed episodes after a tool timeout. A transport timeout must
not trigger another explorer call or allow a later finish to be accepted.
The three additional regression cases cover early transport timeout, episode
deadline expiry, and unchanged exception propagation with review disabled.

`controlled-results.json` is the unmodified JSON downloaded from CI artifact
`11655902721`. Its ZIP SHA-256 was verified as
`f87487603a0127b870917b11cbfba6a4939ba79b280519a321d84c3c3decf9f2`.
The file contains 14 cases, three repetitions, and two arms: 84 episodes with
zero failed runtime gates. Its source digests match the feature revision.
The intentionally false-sufficient semantic negative control is detected in
all three repetitions. These are scripted runtime checks, not retrieval-quality
measurements. Their engineered coverage improvement and simulated tokens are
excluded from live-benefit estimates.

## Preflight result

The following command was attempted after all upstream CI checks passed:

```bash
.venv/bin/python scripts/experiment_evidence_review.py \
  --mode live-reviewer --case complete_control --repeats 1 \
  --output /tmp/knowhere-live-reviewer-preflight.json
```

It exited with code 2 and the sanitized error
`{"status": "error", "error_type": "ValueError"}`. A separate configuration
presence check established that `DS_KEY` is absent, `DS_URL` resolves to a
configured default, and `LLM_MOCK_ENABLED` is false. No credential values were
recorded and no model request was sent. No successful live report was written.
The machine-readable record is `preflight.json`.

To unblock reviewer calibration, configure `DS_KEY` in the execution
environment and select a matching provider endpoint/model using the existing
text-provider configuration. Keep `LLM_MOCK_ENABLED=false`. The small command
above is the first smoke check; after it succeeds, the existing calibration
command is:

```bash
.venv/bin/python scripts/experiment_evidence_review.py \
  --mode live-reviewer --repeats 3 \
  --output /tmp/knowhere-live-reviewer-calibration.json
```

This second command covers the 11 eligible synthetic cases. Explorer and
corpus responses remain scripted, including the evidence revealed after a
correction. Only reviewer calls use a real provider. Report reviewer judgments,
invalid-output and unverified rates, provider-reported reviewer tokens, and
reviewer latency. Do not interpret the fixed explorer token counts or total
episode cost as production measurements. Inspect judgments independently:
exit code 0 means runtime gates passed, not that semantic quality is acceptable.
Record the actual resolved reviewer model before drawing model-specific claims.

## Protocol for end-to-end benefit measurement

This protocol is fixed before live outputs are observed. The representative
corpus, annotated held-out query set, and end-to-end runner are **not yet
prepared**; the existing calibration script cannot substitute for them.

1. Prepare 60 questions over revision-pinned documents: 10 development questions
   and 50 held-out questions. Separate related documents/question families across
   the split. Include complete evidence, multiple requested dimensions, numeric
   tables, conflicting/outdated sources, and questions unanswerable from the
   frozen corpus. Freeze requirements, supporting source spans, contradictions,
   and answerability labels before running the held-out set. Record dataset and
   index digests. Synthetic fixture results remain a separate diagnostic stratum.
2. Run both arms through a real explorer and real corpus search/read tools over
   the same published index, document scope, model settings, and query. Toggle
   only `review_evidence`. Use cold/disabled caches and no prescribed discovery
   pages. Assert that the agentic route was actually exercised; classic or
   small-corpus shortcuts do not test this feature.
3. Preserve the production initial limits: 15 exploration/review steps,
   180 seconds, and at most 1,024 output tokens per completion. Pick turns retain
   production accounting and can add model calls. Episode tokens are measured,
   not capped by `EpisodeBudget`. Review and correction share the original time
   and step budget; no extra allowance is granted to the enabled arm.
   These are equal initial settings, not identical proven hard execution ceilings:
   the legacy disabled path can make an extra forced-finish call and does not
   enforce the same per-await deadline. Record actual steps, duration, forced
   finishes, and deadline overshoots in both arms. If the benchmark adds a common
   outer hard deadline, declare it before running and apply it equally; retain
   those timeouts as failures rather than converting them to successful finishes.
4. Run each held-out question three times in each arm: 300 episodes. Alternate
   arm order within pairs; record the schedule before execution. Run development
   smoke checks first. A provider failure is retained as a failure, not silently
   replaced by a retry or excluded from the denominator.
5. Save the first natural finish packet and the final-visible returned packet,
   exact source revisions, trace, stop reason, actual model identifiers, prompt
   digests, reviewer reports, tokens, usage completeness, and timings. Keep gold
   labels out of explorer/reviewer prompts and retrieval tools.
6. Independently assess semantic requirement coverage and sufficiency against
   the final-visible text/table evidence. The feature's own verdict is never
   the gold label. Chunk IDs and exact quotes alone cannot establish semantic
   sufficiency. Blind the independent assessment to arm and reviewer verdict;
   adjudicate disagreements before computing aggregate results.

## Metrics and interpretation

| Metric | Denominator and interpretation |
|---|---|
| Final gold-sufficient rate | All scheduled episodes, with failures reported separately and counted as no delivered sufficient result. Also show an answerable-only view. |
| Requirement coverage | Independently supported requirements divided by frozen requirements; macro-average by question. Report no-answer cases separately. |
| Incomplete baseline finish | Baseline episodes ending `finished` with insufficient final evidence. This is a retrieval stop, not a sufficiency claim. |
| False sufficient | Enabled episodes claiming `sufficient` whose final packet is independently insufficient. Report per sufficient claim and per insufficient packet. The baseline has no comparable verdict, so its rate is null. |
| False insufficient | Enabled episodes judged `insufficient` despite independently sufficient evidence, divided by independently sufficient enabled packets. |
| Rescue rate | Initially insufficient enabled finish packets becoming independently sufficient after the one permitted correction, divided by initially insufficient packets eligible for correction. |
| Unverified and failures | Separate counts for budget stops, unavailable/invalid review, provider errors, unsupported evidence, and unknown usage. |
| Resource overhead | Actual total and reviewer tokens, provider usage completeness, and p50/p95 latency for each arm. Compute monetary cost only with known pricing and complete relevant usage; otherwise report unknown. |
| Incremental efficiency | Extra measured cost divided by the number of additional gold-sufficient results. Undefined if there is no positive gain or cost is unknown. |

Average repetitions within each question before computing paired deltas.
Bootstrap questions, keeping all repeats and both arms together, for exploratory
95% intervals. Fifty questions provide fifty question-level units, not 150
independent trials. If questions share related documents, preserve those
document-family clusters when resampling. Show raw counts and results by case
family; do not select only favorable examples.

Do not claim a demonstrated benefit solely because runtime gates pass. Positive
coverage/sufficiency deltas need their uncertainty and added cost reported;
false-sufficient events require case-level analysis. Do not infer production
generalization from the synthetic calibration corpus.

Stop on failed provider preflight, a mocked explorer/backend in the end-to-end
arm, gold leakage, missing revision/identity provenance, or a runtime-budget
violation of the declared benchmark policy. Record the known legacy budget
semantics separately from unexpected budget changes. Poor model quality is a
result to retain, not a reason to selectively
restart or omit episodes. Keep the scripted semantic negative control as an
evaluator check outside the real-benefit aggregate.

## Current outcome

CodeQL remediation and regression validation are complete. The controlled
baseline is preserved. Real reviewer calibration is blocked by the absent
provider key, and end-to-end quality/cost measurement has not run. All live
benefit fields remain null in the preflight record.
