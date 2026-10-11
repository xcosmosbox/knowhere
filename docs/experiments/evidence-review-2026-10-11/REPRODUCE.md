# Mac 2026-10-11 continuation: replay, recovery and new measurements

The three original retrieval shards have completed all 144 scheduled episodes, 72 per arm; workers and real blind evaluation have exited. The confirmation has 152 deduplicated blind packets, three passed fresh semantic negative controls and two retained invalid source-span assessments. No started identity or score was retried. The final report is `BENEFIT_REPORT.md`; delivery evidence is described in `RELEASE_VERIFICATION.md`. Documentation/archival commits made after the run are not the measured runtime revision.

## Separate revisions and evidence

- Historical archive: `69166a4db13d82e2396e8e3cb66784c6fff90080`; original measurement and post-measurement reproduction protocols remain separate.
- Final production feature: `d4d32ad74091b4040e1a1e8d7dae10f6a5b222c1`. Three narrow source-span/guard/CI-adapter commits follow the original feature `f68cee2d2793dc4d6fa5cb9281f3d6d357826b1b`.
- Original new unscoped development: `6804b9714b727da4dd8338fb0d23250da1099697`, profile `provider-max-thinking`, 12 completed episodes.
- Scoped development: `94728f6e33aa8620ab6c6fecc533bdfbef792aa6`, profile `provider-max-scoped-thinking`, 12 completed episodes.
- Formal scoped held-out protocol: `6c12e6971cffe900aec98805a78e35d55aca9239`, 402 runtime source fingerprints, 3 logical shards/workers, 24 questions × 3 repeats × 2 arms = 144 scheduled episodes.

The new source inventory is `scripts/fixtures/evidence_review_rfc_20261011/gold.json`. SHA-256 is `2204af014e546eb13a748376efc325ccbac92a5301b7a89c97660a44335e7d67`; corpus digest is `4fa168c54d37d8345ccd8ea6f7568acd75d6d0a0b36622235f7be229d1e1ab6f`. Five complete official RFC texts, including notices, are mechanically windowed without selecting gold passages. Expected new index: 200 chunks/map units and 37,274 token rows. The frozen input digest is `4c0b7eaa6de58d49f7d7ce582300fcfb8352d973ab728d1b991530d7daa16657`; the verified published index digest is separately `ee450ac6b7b0f5cd601aeadddb039b3d81ea5b4348d6051852c2becb504ef081`.

All recovery/new-run files originate from the isolated local run directory `runs/mac-takeover-20261011-2r2hML`. They are not production deployment state.

The question set is a custom, project-built frozen inventory, not an official benchmark. Only its full RFC source texts are official. Confirmation has 20 answerable and four partially unanswerable questions in two families (JSON/QUIC); experimental holdout is not proof of absence from model pretraining.

## Verify/extract archives before replay

Completed-stage archives have separate `*.manifest.json` files. Verify each archive size/hash and every regular member size/hash. Reject absolute paths, `..`, links, devices and unexpected members before extracting with Python 3.12's `filter='data'` into a new, dedicated directory. Do not overwrite historical or live run directories. Archive member paths start with `mac-takeover-20261011/`.

Archives are deterministic gzip/tar files: sorted regular members, gzip/tar mtime 0, uid/gid 0 and mode 0644. Databases, venvs, dependency checkouts, the private key and provider `reasoning_content` are excluded. The exact experimental native tokenizer is an explicit separate component archive with its MIT license, not a full dependency checkout.

- `mac-restoration-records`: copied-history replay/index/environment checks, successful and failed smoke protocols/records, original native build configuration.
- `mac-development-records`: both distinct 12-episode RFC development runs, independent blind assessments, summaries, first control records and offline source audits.
- `mac-validation-records`: regression XML, failed and repaired controlled audits, original independent code-review finding and follow-up, exact-head CI observation, fork history-scanner diagnosis and the in-progress PR update.
- `mac-native-tokenizer`: the exact arm64 BlingFire 0.1.8 library, build metadata and license.
- `mac-heldout-records`: all 144 scheduled records, real blind evaluation/summary and source/fingerprint audit, 31 members, archive SHA-256 `2d41a923707a48e5a0b66115f0af4b72de61a6b16a3941874fee15ba62507f5b`. All five Mac stage archives total 123 verified members.
- `mac-release-evidence`: independent arithmetic draft, checks/tools, original archive/report helper failures and offline guard repair, source audit, raw scanner findings and exact fingerprint classification, all-member verification, late network/non-convergence observations and final PR responses. The supplemental archive is immutable; its own final hash/member/scan verification is retained in separate sidecars to avoid self-reference.

Preserve failed raw gates and interrupted starts. A recalculated report is a separate file; never rewrite the historical primary or sensitivity scores.

## Mac environment

The actual host uses native arm64 macOS 26.2, Python 3.12.14 and Node 22.23.1. `uv.lock` and PGlite locks were not changed. PGlite is 0.5.8/socket 0.2.11 and retains the existing SSL/Terminate fixes. Each worker has its own database and serial episodes.

Use an isolated checkout/venv of the requested frozen revision. Install with:

```text
uv sync --locked --all-packages --all-groups --python 3.12.14
npm ci --prefix scripts/evidence_review_benchmark/pglite --ignore-scripts
```

The locked BlingFire wheel contained an x86_64 dylib. This run rebuilt exactly upstream v0.1.8 revision `d9d5cea9cb7f5abbe650ef348c4010dce0658043` as arm64, preserving the original library and failed preflight. The actual library hash is `86444de096909758773cf48561b74bdeec1806d68d08bf228e25303419aa24d9`. Verify the native archive and installed hash for exact local protocol replay. Compiler/path changes may change binary identity; if a rebuild differs, verify index equivalence and freeze a separately labeled reproduction protocol instead of editing the old tokenizer hash.

Mac pytest-postgresql imports require libpq discovery. The actual isolated workaround is:

```text
DYLD_LIBRARY_PATH=/Users/ottofeng/Desktop/knowhere/runs/mac-takeover-20261011-2r2hML/libpq
```

API/worker database contracts also use an isolated native PostgreSQL 16.2 executable with source-built `pg_trgm` and `uuid-ossp`; this did not replace the benchmark's PGlite backend. Source/build metadata is archived. API and worker suites must run sequentially because their test storage helpers share a temporary root. Do not change DNS, assertions or security validation to hide the baseline-reproduced Mac `example.com` DNS failure.

The four benchmark test modules need ordinary offline application settings. A no-live-key invocation is:

```sh
env DYLD_LIBRARY_PATH=/ABS/LIBPQ_DIR \
  S3_BUCKET_NAME=benchmark-unused S3_TEMP_PATH=/tmp \
  TMP_PATH=/tmp/knowhere-evidence-experiment \
  DATABASE_URL=postgresql+asyncpg://test:test@localhost/test \
  DS_KEY=offline-test-placeholder \
  .venv/bin/python -m pytest \
  scripts/evidence_review_benchmark/test_score.py \
  scripts/evidence_review_benchmark/test_runtime.py \
  scripts/evidence_review_benchmark/test_frozen_inventory.py \
  scripts/evidence_review_benchmark/test_resources.py -q
```

Expected configured scope is 136 passed. The earlier missing-libpq startup and 89-pass/1-missing-config subset invocation are separately retained; they are not erased by the correctly configured run.

## Offline summary replay

After validating/extracting the final archive and checking out the measured runtime sources, set `KNOWHERE_REPLAY_DIR` to the extracted `mac-takeover-20261011/rfc-heldout-scoped-v3` directory. Use a new summary output directory:

```sh
.venv/bin/python scripts/evidence_review_benchmark/summarize.py \
  --gold scripts/fixtures/evidence_review_rfc_20261011/gold.json \
  --protocol "$KNOWHERE_REPLAY_DIR/protocol.json" \
  --split held_out --pricing-date 2026-10-11 \
  --trials "$KNOWHERE_REPLAY_DIR/shard-0/trials.jsonl" \
           "$KNOWHERE_REPLAY_DIR/shard-1/trials.jsonl" \
           "$KNOWHERE_REPLAY_DIR/shard-2/trials.jsonl" \
  --assessments "$KNOWHERE_REPLAY_DIR/assessments" \
  --output /NEW/EMPTY/REPLAY_SUMMARY
```

This uses saved assessments and makes no model calls. Input-path keys can differ across machines; compare hash values and metrics, not absolute path spellings. Requirements, source provenance, packet mapping and the full frozen denominator remain mandatory.

## Original recovery contract (do not restart this completed run)

The following command documents the original worker contract, not authorization to restart this finished dataset. Never launch a second copy against active worker/database/output or extend the completed confirmation. For any separately authorized recovery, inspect process identity, `started.jsonl`, `trials.jsonl` and provider events first. Completed IDs are skipped. A started ID lacking a final row becomes an interrupted failure with unknown resource use and is never resent. In-flight server cancellation and billing cannot be inferred from local termination.

The original worker command, with `N` replaced by its original 0/1/2 shard, was:

```sh
env DYLD_LIBRARY_PATH=/ABS/LIBPQ_DIR \
node scripts/evidence_review_benchmark/pglite/run-with-pglite.mjs \
  --data-dir "$KNOWHERE_RUN_DIR/db-N" -- \
  .venv/bin/python scripts/evidence_review_benchmark/run.py \
  --key-file /PRIVATE/EXISTING/DEEPSEEK_KEY_FILE \
  --gold scripts/fixtures/evidence_review_rfc_20261011/gold.json \
  --resource-profile provider-max-scoped-thinking \
  --protocol "$KNOWHERE_RUN_DIR/protocol.json" \
  --output "$KNOWHERE_RUN_DIR/shard-N" \
  --split held_out --shards 3 --shard N --workers 3
```

Use `caffeinate` bound to the actual known worker/finalization process, and retain process IDs. There is no local episode/API/output-byte or monetary ceiling. Maximum output is the provider's 393,216-token API ceiling with thinking enabled/max; ignored thinking temperature is omitted. Two reviews/one correction and source/schema/final-fingerprint checks remain workflow invariants. Ordinary database/Redis operation safety settings remain existing infrastructure behavior, not a DeepSeek spending policy.

Keep the Mac open and online: an idle-sleep assertion does not override clamshell sleep. The formal run's power log records a 922-second clamshell sleep at 2026-10-11 12:28:11 +08:00, followed by DarkWake at 12:43:33. Three in-flight episodes overlapping that interval ended with connection errors; the earlier fourth connection failure did not overlap it. Temporal overlap is not proof of a sole cause. All failures remain in the scheduled denominator and are never resent. Original `time.perf_counter()` durations are retained, with independently calculated UTC elapsed durations reported separately because the clocks differ during host sleep. No global power settings were changed.

The log's `Total chunks in scope: 2` is an intentionally bounded small-corpus precheck: `count_scoped_chunks(max_count=top_k+1)` with `top_k=1`. It is not the true source-unit count. Actual scope is verified through the frozen manifest, request document IDs, real tools and context-local exact full-read receipts.

## New measurements and independent evaluation

For a new paid observation, use a new run directory/protocol and freeze before any call. Never extend this observed dataset and call the extension unseen confirmation. Any change in source, model settings, inventory, prompts, evaluator or validation requires a separate protocol and explicit interpretation.

The completed pipeline called the following only after all 144 scheduled identities had final records. Do not rerun it to replace saved scores:

```sh
.venv/bin/python scripts/evidence_review_benchmark/evaluate.py \
  --key-file /PRIVATE/EXISTING/DEEPSEEK_KEY_FILE \
  --gold scripts/fixtures/evidence_review_rfc_20261011/gold.json \
  --protocol "$KNOWHERE_RUN_DIR/protocol.json" \
  --resource-profile provider-max-scoped-thinking \
  --trials "$KNOWHERE_RUN_DIR/shard-0/trials.jsonl" \
           "$KNOWHERE_RUN_DIR/shard-1/trials.jsonl" \
           "$KNOWHERE_RUN_DIR/shard-2/trials.jsonl" \
  --output "$KNOWHERE_RUN_DIR/assessments" --concurrency 4
```

This makes real paid calls: three fresh semantic negative controls, then one call per deduplicated arm-blinded packet, including eligible first-finish snapshots. Failed or interrupted assessments remain unknown; there are no retries until a desired score. Evaluation is the same DeepSeek family, not independent-model or human truth. Scoring cost is separate from retrieval cost. Dates/usage missing from a call remain unknown, not zero; the October 11 estimate cannot be silently applied to another UTC date.

The production explorer rebuilds a fresh system/user prompt with tool trace/latest results each action; it is not the provider's native assistant/tool conversation with retained `reasoning_content`. Thinking is enabled on every actual call, but previous private reasoning is not carried into the next action. Both arms share that architecture. A no-tool-call stop is retained as model/workflow behavior, not relabeled as truncation or repaired by parsing pretend tool XML. Studying a native thinking conversation would be a separate experimental factor.

Final reporting must aggregate repeats within questions, keep all 72 scheduled episodes per arm, list delivery failures and semantic unknowns, separate literal span recall from entailment, and report claim denominators, effective review validity, actual correction attempts/rescues, usage/cache, latency and dated costs. Do not infer a production quality gain merely from green CI or successful development calls.

## Completed-run offline accounting and safe observation

No model request is needed to inspect the original run. On this host:

```sh
KNOWHERE_OBSERVE_RUN=/Users/ottofeng/Desktop/knowhere/runs/mac-takeover-20261011-2r2hML
/Users/ottofeng/Desktop/knowhere/knowhere/.venv/bin/python "$KNOWHERE_OBSERVE_RUN/heldout_progress.py" --compact
tail -n 12 "$KNOWHERE_OBSERVE_RUN/rfc-heldout-scoped-v3/evaluation.log"
less "$KNOWHERE_OBSERVE_RUN/rfc-heldout-scoped-v3/summary/RESULTS.md"
```

These only read durable journals. No private key file or private reasoning should be opened for observation. Three shards now each have 48 final records and no active IDs. A completed count only advances when an episode has a final row: repeated successful provider requests during a long episode do not advance it. This explains the earlier apparent stall near 122, not proof of a dead worker.

After safely extracting stage and supplemental archives into one new directory, the independent helper can recompute arithmetic to a new empty output with no API calls:

```sh
python prepare_benefit_report.py --experiment /EXTRACTED/mac-takeover-20261011/rfc-heldout-scoped-v3 --split held_out --output /NEW/EMPTY/ACCOUNTING
```

Use the frozen lab checkout containing the gold and input sources. Original absolute paths may differ; this helper was written for the documented local checkout, so inspect/rebase only analysis input-location references in a separately labeled replay copy, never the measured protocol/hashes. All-member verifier also has an original-host private-key-file safety check; do not pretend its absence elsewhere proves the archive was credential-free. Validate public manifests and member hashes independently before extraction.

The original arithmetic draft's correction total four means the sum of nonmissing public counters. Two failed episodes additionally have captured insufficient reviewer outputs and subsequent corrective exploration; missing public counters stay unknown, and those first packets are not independently scored as eligible first finishes. See `failed-review-activity-observation.json` in supplemental evidence.

Original archive/report companions failed because a marker-substring guard rejected its own quoted PEM detector source. The post-run offline repair added material-aware and decoded-JSON checks without path exemptions; 36 guard/accounting tests passed with unrelated pytest plugin autoload disabled. The first missing-libpq plugin invocation failure is preserved as a summary, not an invented raw traceback. No real-model retry was involved. Existing immutable archives were not rewritten.

The unmodified recursive scanner exited 1 on 132 exact historical source fingerprints; each was verified against its protocol-recorded Git revision. Keep the raw scanner status/findings and classification separate; classification does not turn the original scan green. Final release scan/verification sidecars record the supplemental set without changing scanner allowlists or history.
