## Summary

- Add support for parsing `.csv` document files through the existing markdown pipeline
- CSV files are read with pandas, converted to structured text representation (heading with row/column metadata + pipe-delimited data rows), then routed through `parse_md()` for hierarchy reconstruction and LLM enrichment
- Handles edge cases: empty CSV files fallback gracefully, pandas parse failures fallback to raw text, NaN values converted to empty strings, overly long cell content truncated at 200 chars
- No API, worker deployment, or migration impact — this is a new format adapter that extends the existing `DocumentFormat` enum and routing logic

## Verification

- `pytest apps/worker/tests/contract/test_csv_parser_contract.py -v` — all 3 tests pass (2 contract tests + 1 unit test)
- `pytest apps/worker/tests/contract/ -v` — all 52 contract tests pass with zero regressions
- Contract tests verify: full pipeline integration via `checkerboard_parse_output()`, DataFrame column contract, content extraction, empty file handling
- Unit test verifies: NaN/missing value handling in `_csv_df_to_md_lines()`

## Deployment Notes

- No new environment variables
- No database migrations, queue changes, or storage changes
- No new dependencies — `pandas` is already a declared dependency in `apps/worker/pyproject.toml`
- Fully backwards compatible; no rollback concerns

## Checklist

- [x] Tests were added or updated when behavior changed
- [x] Public docs, examples, or OpenAPI contracts were updated when needed
- [x] Database migrations are idempotent and safe to deploy
- [x] Logs, errors, and validation paths avoid leaking secrets or user data
- [x] The pull request description explains any breaking or user-visible change
