"""Contract tests for the CSV format parser.

Verifies that .csv files are correctly routed through the
CsvParseAdapter and produce valid ParseOutput. This test also
serves as a regression test for the gap where CSV was listed
as "supported" in the README but had no parser routing.
"""

from __future__ import annotations

import csv
from pathlib import Path


def _write_contract_csv(test_csv_path: Path) -> None:
    """Write a realistic CSV file for contract testing.

    Contains sales data with multiple columns and data types
    (strings, integers, floats).
    """
    with open(test_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Region", "Product", "Units", "Revenue", "Margin"])
        writer.writerow(["North", "Widget A", "120", "24000.00", "0.35"])
        writer.writerow(["South", "Widget B", "85", "17000.00", "0.28"])
        writer.writerow(["East", "Widget A", "200", "40000.00", "0.42"])
        writer.writerow(["West", "Widget C", "65", "13000.00", "0.31"])
        writer.writerow(["North", "Widget B", "45", "9000.00", "0.22"])


def test_csv_parser_contract_produces_valid_parse_output(
    worker_contract_environment: None,
    tmp_path: Path,
) -> None:
    """Verify that a .csv file is routed through the CsvParseAdapter
    and produces a ParseOutput with the expected DataFrame contract."""
    from app.services.document_parser.parse_service import checkerboard_parse_output

    csv_path = tmp_path / "sales.csv"
    output_root = tmp_path / "parser-output"
    _write_contract_csv(csv_path)

    parse_output = checkerboard_parse_output(
        file_full_path=str(csv_path),
        filename="sales.csv",
        output_dir=str(output_root),
        internal_output_filename="sales.csv",
        summary_image=False,
        summary_table=False,
        summary_txt=False,
        smart_title_parse=False,
        stopwords=[],
    )

    full_output_dir = parse_output.output_dir
    parsed_df = parse_output.parsed_df

    # ── Output directory contract ───────────────────────────────
    assert full_output_dir.endswith("sales.csv"), (
        f"Expected output directory to end with 'sales.csv', "
        f"got: {full_output_dir}"
    )
    assert parsed_df is not None, (
        "Expected parsed_df to be non-None for CSV input"
    )

    # ── DataFrame column contract ───────────────────────────────
    expected_columns = ["path", "content", "type", "summary", "keywords"]
    for col in expected_columns:
        assert col in parsed_df.columns, (
            f"Expected column '{col}' in parsed_df, "
            f"got columns: {list(parsed_df.columns)}"
        )

    # ── Content extraction: verify CSV data appears in output ───
    all_content = " ".join(str(c) for c in parsed_df["content"].tolist() if c)
    assert "Region" in all_content, (
        "Expected header 'Region' in parsed output"
    )
    assert "Widget A" in all_content, (
        "Expected data value 'Widget A' in parsed output"
    )
    assert "North" in all_content, (
        "Expected data value 'North' in parsed output"
    )

    # ── Path contract ───────────────────────────────────────────
    paths = parsed_df["path"].tolist()
    assert any(p.startswith("sales.csv") for p in paths), (
        f"Expected at least one path starting with 'sales.csv', "
        f"got paths: {paths}"
    )


def test_csv_parser_handles_empty_file(
    worker_contract_environment: None,
    tmp_path: Path,
) -> None:
    """Verify that an empty CSV file is handled gracefully without crash."""
    from app.services.document_parser.parse_service import checkerboard_parse_output

    csv_path = tmp_path / "empty.csv"
    csv_path.write_text("", encoding="utf-8")
    output_root = tmp_path / "parser-output"

    parse_output = checkerboard_parse_output(
        file_full_path=str(csv_path),
        filename="empty.csv",
        output_dir=str(output_root),
        internal_output_filename="empty.csv",
        summary_image=False,
        summary_table=False,
        summary_txt=False,
        smart_title_parse=False,
        stopwords=[],
    )

    # Should produce output without crashing (best-effort).
    assert parse_output is not None


def test_csv_df_to_md_lines_handles_missing_values() -> None:
    """Unit test: _csv_df_to_md_lines should handle NaN/missing values
    by converting them to empty strings."""
    import pandas as pd

    from app.services.document_parser.formats.csv.parser import _csv_df_to_md_lines

    df = pd.DataFrame({
        "Name": ["Alice", "Bob"],
        "Score": [95, None],
        "Notes": [None, "Passed with honors"],
    })
    lines = _csv_df_to_md_lines(df)

    # Row for Alice (Score=95, Notes=empty)
    alice_line = [l for l in lines if "Alice" in l][0]
    assert "95" in alice_line, f"Expected '95' in Alice line, got: {alice_line}"

    # Row for Bob (Score=empty, Notes="Passed with honors")
    bob_line = [l for l in lines if "Bob" in l][0]
    assert "Passed with honors" in bob_line, (
        f"Expected notes in Bob line, got: {bob_line}"
    )
