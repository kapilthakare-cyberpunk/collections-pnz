#!/usr/bin/env python3
"""
Generate a quick balance-sum report from a rental invoicing CSV.

It sums the entire "Balance" column (no filtering) and reports the total.
Expected columns (case-sensitive):
  - Balance    : outstanding balance per invoice (numeric)
  - Inv Date   : invoice date (optional; used for min/max info)
  - Order No   : optional; used for counts
  - Inv No     : optional; used for counts
  - Billing Name / Customer : used to infer customer name if not provided
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd


def select_input_file() -> Optional[Path]:
    """Offer an interactive selection of recent CSV files in the current directory."""
    csv_files = sorted(Path(".").glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not csv_files:
        print("No CSV files found in the current directory.", file=sys.stderr)
        return None

    print("Select a CSV file:")
    for idx, path in enumerate(csv_files, start=1):
        mtime = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        print(f"  {idx}) {path.name} (modified {mtime})")
    print("  0) Enter a custom path")

    try:
        choice_raw = input("Enter choice: ")
    except EOFError:
        print("No input received; provide --input to skip interactive mode.", file=sys.stderr)
        return None

    try:
        choice = int(choice_raw.strip())
    except ValueError:
        print("Invalid selection.", file=sys.stderr)
        return None

    if choice == 0:
        custom = input("Enter path to CSV: ").strip()
        return Path(custom) if custom else None
    if 1 <= choice <= len(csv_files):
        return csv_files[choice - 1]

    print("Selection out of range.", file=sys.stderr)
    return None


def infer_customer_name(df: pd.DataFrame) -> Optional[str]:
    """Try to infer the customer name from common columns."""
    candidate_columns = ["Billing Name", "Customer Name", "Customer"]
    for col in candidate_columns:
        if col not in df.columns:
            continue
        series = df[col].dropna()
        if series.empty:
            continue
        if not pd.api.types.is_string_dtype(series):
            continue
        values = series.astype(str).str.strip()
        values = values[values != ""]
        uniques = values.unique()
        if len(uniques) == 1:
            return uniques[0]
    return None


def build_balance_report(df: pd.DataFrame, customer: str, as_of: datetime) -> str:
    df = df.copy()
    df["Inv Date"] = pd.to_datetime(df.get("Inv Date"), errors="coerce")

    payable = df[df["Balance"] > 0].copy()
    balance_total = float(payable["Balance"].sum())
    order_count = payable["Order No"].nunique() if "Order No" in payable.columns else int(payable.shape[0])

    min_date = payable["Inv Date"].min() if "Inv Date" in payable.columns else None
    max_date = payable["Inv Date"].max() if "Inv Date" in payable.columns else None

    lines = []
    lines.append(f"Balance Summary — {customer} (as of {as_of:%d-%b-%Y})")
    lines.append("")
    lines.append(f"1) Total balance payable as of today: Rs {int(balance_total):,}")
    lines.append("")
    lines.append(f"2) Total number of orders with balance payable: {order_count}")
    lines.append("")
    if pd.notna(min_date) or pd.notna(max_date):
        min_str = min_date.strftime("%d-%b-%Y") if pd.notna(min_date) else "N/A"
        max_str = max_date.strftime("%d-%b-%Y") if pd.notna(max_date) else "N/A"
        lines.append("3) Unpaid invoice date range")
        lines.append(f"   From {min_str} to {max_str}")
    else:
        lines.append("3) Unpaid invoice date range")
        lines.append("   No unpaid invoices found.")

    lines.append("")
    lines.append("Notes")
    lines.append(" - Only invoices with Balance > 0 are counted.")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sum the Balance column and report totals.")
    parser.add_argument(
        "input",
        nargs="?",
        help="Path to the CSV file. If omitted, you'll be prompted to pick a recent CSV in this folder.",
    )
    parser.add_argument(
        "--input",
        dest="input_opt",
        help="Path to the CSV file (optional; same as positional input).",
    )
    parser.add_argument("--customer", default="Customer", help="Customer name for the header.")
    parser.add_argument(
        "--as-of",
        default=datetime.today().strftime("%Y-%m-%d"),
        help="As-of date in YYYY-MM-DD format (default: today).",
    )
    parser.add_argument(
        "--output",
        help="Optional output path. Defaults to 'Balance Summary - <customer> (as of <date>).txt' next to the input.",
    )
    args = parser.parse_args()

    input_arg = args.input or args.input_opt
    input_path = Path(input_arg) if input_arg else select_input_file()
    if not input_path:
        parser.error("No input file provided.")
    if not input_path.exists():
        parser.error(f"Input file not found: {input_path}")

    as_of = datetime.strptime(args.as_of, "%Y-%m-%d")

    df = pd.read_csv(input_path)
    if "Balance" not in df.columns:
        raise ValueError("Input missing required column: Balance")

    customer = args.customer
    if customer == "Customer":
        inferred = infer_customer_name(df)
        if inferred:
            customer = inferred

    report_text = build_balance_report(df, customer, as_of)

    output_path = (
        Path(args.output)
        if args.output
        else input_path.with_name(f"Balance Summary - {customer} (as of {as_of:%d-%b-%Y}).txt")
    )
    output_path.write_text(report_text)
    print(f"Wrote balance report: {output_path}")


if __name__ == "__main__":
    main()
