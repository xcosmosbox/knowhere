# pyright: reportArgumentType=false, reportAttributeAccessIssue=false, reportCallIssue=false, reportReturnType=false
"""CSV document parser.

Reads .csv files with pandas and converts tabular data into
markdown-like text lines for the standard parse_md() pipeline.

CSV files are treated as structured tabular documents: the header
row becomes a markdown heading, and each data row is converted to
a pipe-delimited text line. The result is fed through parse_md()
for hierarchy reconstruction and heading detection.
"""

from __future__ import annotations

import pandas as pd


def parse_csv(
    output_dir: str,
    source_type: str,
    file_path: str,
    base_llm_paras=None,
    relative_root: str | None = None,
):
    """Parse a CSV file into a hierarchical document DataFrame.

    Reads the CSV with pandas, converts it to a structured text
    representation (header metadata + pipe-delimited rows), and
    delegates to parse_md() for heading detection and hierarchy
    reconstruction.

    Args:
        output_dir: Full output directory path for parsed artifacts.
        source_type: Source type label (always "csv" from the adapter).
        file_path: Absolute path to the .csv file on disk.
        base_llm_paras: LLM parameter dict for summary enrichment.
        relative_root: Root path segment for hierarchical path construction.

    Returns:
        pd.DataFrame with columns [path, content, type, summary, keywords]
        representing the parsed document hierarchy.
    """
    from app.services.document_parser.formats.markdown.parser import parse_md

    # Read the CSV file with pandas — we use its robust CSV parser
    # which handles quoting, escaping, and encoding detection.
    try:
        df = pd.read_csv(file_path)
    except Exception:
        # If pandas can't parse the CSV, fall back to treating it
        # as plain text so parse_md() can still extract content.
        from app.services.common.file_loading import load_file_bytes

        raw = load_file_bytes(file_path, file_url="")
        md_lines = raw.decode("utf-8", errors="replace").splitlines()
    else:
        md_lines = _csv_df_to_md_lines(df)

    parsed_df = parse_md(
        output_dir,
        source_type=source_type,
        md_lines=md_lines,
        base_llm_paras=base_llm_paras,
        relative_root=relative_root,
    )
    return parsed_df


def _csv_df_to_md_lines(df: pd.DataFrame) -> list[str]:
    """Convert a pandas DataFrame into markdown-like text lines.

    Produces:
    1. A heading line with column count and row count metadata.
    2. A header row with column names (pipe-delimited).
    3. Data rows (pipe-delimited), one per line.

    Args:
        df: pandas DataFrame read from the CSV file.

    Returns:
        List of text lines suitable for the parse_md() pipeline.
    """
    lines: list[str] = []

    # Header metadata: document-level heading describing the table.
    cols = list(df.columns)
    row_count = len(df)
    col_count = len(cols)
    lines.append(f"# CSV Table ({row_count} rows × {col_count} columns)")

    # Column headers as a pipe-delimited reference line.
    header_line = " | ".join(str(c) for c in cols)
    lines.append(header_line)

    # Data rows: convert each row to a pipe-delimited text line.
    # We limit cell content to avoid excessively long lines that
    # could degrade markdown parsing quality.
    _MAX_CELL_CHARS = 200

    for _, row in df.iterrows():
        cells: list[str] = []
        for col in cols:
            val = str(row[col]) if pd.notna(row[col]) else ""
            if len(val) > _MAX_CELL_CHARS:
                val = val[:_MAX_CELL_CHARS] + "…"
            cells.append(val)
        lines.append(" | ".join(cells))

    return lines
