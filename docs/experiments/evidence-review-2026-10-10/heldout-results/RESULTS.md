# Held-out evidence-review results

Descriptive results for all 50 frozen held-out questions, three repeats and two arms (300 episodes). Repeats are averaged within questions. There are only two document families; no population significance claim or p-value is made.

| Stratum | Baseline confirmed sufficient | Review confirmed sufficient | Paired sufficiency delta (percentage points) | Paired semantic coverage delta (percentage points) |
|---|---:|---:|---:|---:|
| All held-out | 121/150 | 118/150 | unknown | unknown |
| micron | 63/75 | 62/75 | unknown | unknown |
| spacex | 58/75 | 56/75 | unknown | unknown |

Confirmed counts are lower bounds if semantic scores are unknown. Delivery failures remain in the scheduled denominator; unknown assessments are reported separately and are not treated as definite semantic failures.

| Arm | Answerable sufficient | Unknown semantic scores | Delivery errors | Latency p50/p95 (s) | Observed real tokens | Complete usage | Estimated USD |
|---|---:|---:|---:|---:|---:|---|---:|
| baseline | 121/126 | 9 | 0 | 6.135/28.086 | 7,511,956 | true | 0.441 |
| review | 118/126 | 10 | 0 | 9.320/27.300 | 8,245,616 | true | 0.526 |

Review made 66 sufficient claims: 0 independently false among 66 scored claims, with 0 unverified claims. False-insufficient decisions: 0 among 118 independently sufficient delivered packets.

Observed first-to-final sufficiency flips: 2 among 5 recorded initially insufficient first finishes. Among 3 actual correction attempts, 2 became sufficient, including 2 with changed evidence. This is not an independent budget-eligibility estimate; 0 unchanged-evidence flips may reflect evaluator variability. Initial unknown scores: 5; relevant final unknown scores: 0. Incremental estimated USD per additional sufficient delivery: unknown.

Offline semantic evaluation is separate: 206 real provider calls, estimated USD 0.114; none of this cost is added to retrieval overhead. All three explicit semantic negative controls passed.

Costs are list-rate estimates, not bills. Only calls dated 2026-10-10 UTC use the Saturday off-peak rates: USD 0.003 per million cached input tokens, 0.15 per million uncached input tokens, and 0.6 per million output tokens. Missing usage or other dates leave total cost unknown; observed cache hits and misses are retained separately in summary.json.

The corpus is deterministic text derived from four checked-in documents. Both arms receive the known document scope. This tests the production retrieval core and tools on PGlite; it does not measure PDF/image understanding, document discovery, HTTP/API workers, native PostgreSQL concurrency or production traffic. The judge uses a separate blind prompt and frozen gold, but shares the DeepSeek model family with the agent, so correlated errors remain possible. Literal quote coverage is not semantic correctness.

Equal initial production budgets do not imply identical hard execution ceilings: legacy baseline forced finishes/retries and actual overruns are retained. Development infrastructure failures and synthetic calibration are excluded from held-out benefit metrics. Detailed stops, errors, steps, latency, unknowns, source-mapping limitations, question-level paired deltas and provider accounting are in summary.json.
