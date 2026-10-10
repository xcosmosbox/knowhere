# Reproduction and record layout

Run commands from the repository root. Python 3.12.14 and the exact selected
dependency versions are recorded in `protocol-heldout.json`; Node 22 or later
and the checked-in PGlite lockfile are required for a new real-tool run.

## Replay saved results without model requests

The archive manifests list the SHA-256 and size of each compressed archive and
every contained file. All archives contain relative paths under this experiment
directory. Verify their hashes, then extract them:

```bash
KNOWHERE_EVAL_DIR=docs/experiments/evidence-review-2026-10-10
for archive in calibration-development-records heldout-traces heldout-assessments audit-records corpus-records; do
  tar -xzf "$KNOWHERE_EVAL_DIR/$archive.tar.gz" -C "$KNOWHERE_EVAL_DIR"
done

.venv/bin/python scripts/evidence_review_benchmark/summarize.py \
  --trials "$KNOWHERE_EVAL_DIR"/heldout/shard-{0..6}/trials.jsonl \
  --assessments "$KNOWHERE_EVAL_DIR/heldout-evaluation" \
  --output /tmp/knowhere-recomputed-primary

.venv/bin/python scripts/evidence_review_benchmark/audit_summary.py \
  --base "$KNOWHERE_EVAL_DIR"
```

These commands use saved judgments and make no API requests. The first aggregate
is separate from the archived primary result. The second deterministically
recreates `audit-sensitivity.json`, validates every audit citation and preserves
the original automated judgments.

The archives contain:

- `calibration-development-records.tar.gz`: real-reviewer scripted calibration,
  the original failed development attempt, corrected development episodes and
  their independent assessments. These are excluded from held-out estimates.
- `heldout-traces.tar.gz`: all seven shards, all 300 original episode records,
  started-request journals, safe provider event metadata and index verification.
- `heldout-assessments.tar.gz`: all 203 unique blinded packets, their 300 episode
  mappings, three negative-control repetitions, 206 assessment records and the
  assessment started-request journal. Invalid assessments remain invalid.
- `audit-records.tar.gz`: the exact inputs and independently written judgments
  for the preselected, invalid-assessment/rescue and symmetric paired-difference
  audits. Cross-model agent judgments are not human labels.
- `corpus-records.tar.gz`: the complete source-offset/revision mapping manifest
  for the derived text corpus, including preserved original page metadata.

## Run a new experiment

The measured runner was frozen in commit
`2ccb9e80e1612595bca248d32b0ea33939347f9d`; its exact file hashes are in
`protocol-heldout.json`. The only later runner behavior change repairs a false
budget-equality gate, after all 300 episodes and offline assessments completed.
Its provenance and regression checks are in `benchmark-gate-fix.json`.
`protocol-reproduction-v2.json` describes the corrected current harness and is
explicitly **not** the protocol used to produce the archived observations.
Never point a new protocol at the archived output directories or database files.

Install the locked workspace and benchmark dependencies:

```bash
uv sync --locked --all-packages --all-groups --python 3.12.14
npm ci --prefix scripts/evidence_review_benchmark/pglite --ignore-scripts
```

Set `KNOWHERE_BENCHMARK_KEY_FILE` to the local file containing the test provider
credential. The runner uses the public request-scoped provider override and the
literal model name `deepseek-flash`; it does not change the production model
default. No model request is made by `--freeze`.

```bash
.venv/bin/python scripts/evidence_review_benchmark/run.py \
  --key-file "$KNOWHERE_BENCHMARK_KEY_FILE" \
  --freeze --protocol /tmp/knowhere-new-protocol.json \
  --output /tmp/knowhere-new-run

knowhere_worker_pids=()
for shard in 0 1 2 3 4 5 6; do
  node scripts/evidence_review_benchmark/pglite/run-with-pglite.mjs \
    --data-dir "/tmp/knowhere-new-db-$shard" -- \
    .venv/bin/python scripts/evidence_review_benchmark/run.py \
    --key-file "$KNOWHERE_BENCHMARK_KEY_FILE" \
    --protocol /tmp/knowhere-new-protocol.json \
    --output "/tmp/knowhere-new-run/shard-$shard" \
    --split held_out --shards 7 --shard "$shard" \
    > "/tmp/knowhere-new-shard-$shard.log" 2>&1 &
  knowhere_worker_pids+=("$!")
done
knowhere_workers_failed=0
for knowhere_worker_pid in "${knowhere_worker_pids[@]}"; do
  wait "$knowhere_worker_pid" || knowhere_workers_failed=1
done
if [ "$knowhere_workers_failed" -ne 0 ]; then
  exit 1
fi

.venv/bin/python scripts/evidence_review_benchmark/evaluate.py \
  --key-file "$KNOWHERE_BENCHMARK_KEY_FILE" \
  --trials /tmp/knowhere-new-run/shard-{0..6}/trials.jsonl \
  --output /tmp/knowhere-new-assessments

.venv/bin/python scripts/evidence_review_benchmark/summarize.py \
  --trials /tmp/knowhere-new-run/shard-{0..6}/trials.jsonl \
  --assessments /tmp/knowhere-new-assessments \
  --output /tmp/knowhere-new-summary
```

Check all shard exit statuses and logs before scoring. The aggregator requires
a complete, unique held-out schedule and preserves failures. Resume the identical
command and protocol only for absent IDs; a started request without a completed
record becomes an interrupted failure and is never automatically replaced.
Seven isolated database workers were used in the measured run. Different worker
counts or hardware can change latency; changing provider versions and caching
can change outputs despite temperature zero.

The dated cost calculator intentionally reports unknown monetary totals for
other dates. Record the provider's applicable prices separately for any new run.
This observed question inventory can reproduce the benchmark, but it is no
longer an unseen confirmation set for changes tuned after reading these results.

## Verification commands

```bash
.venv/bin/python -m pytest scripts/evidence_review_benchmark/test_score.py scripts/evidence_review_benchmark/test_runtime.py -q
.venv/bin/python scripts/evidence_review_benchmark/summarize.py --self-test
.venv/bin/ruff check scripts/evidence_review_benchmark
git diff --check
```

Production feature CI separately passed 961 tests, lint, typecheck, secret
scanning and CodeQL at the recorded feature revision. The test provider and
offline scorer do not exercise API authentication, billing, ingestion workers,
PDF/image parsing, live Cursor execution or native database concurrency.
