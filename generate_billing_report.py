#!/usr/bin/env python3
"""
Generate a billing summary report from a rental invoicing CSV.

Expected columns (case-sensitive):
  - Inv Date : invoice date (YYYY-MM-DD or similar, parseable by pandas)
  - Inv Value: invoice amount (numeric)
  - Balance  : outstanding balance per invoice (numeric)
  - Order No : order identifier
  - Inv No   : invoice identifier

Usage examples:
  python3 generate_billing_report.py --input anay-deshpande-28-nov-2025.csv \\
    --customer "Anay Deshpande" --as-of 2025-11-28

  python3 generate_billing_report.py --input data.csv

Outputs a txt report next to the input file. You can override the output path.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd


def fy_label(date: pd.Timestamp) -> Optional[str]:
    if pd.isna(date):
        return None
    start = date.year if date.month >= 4 else date.year - 1
    return f"FY{start}-{(start + 1) % 100:02d}"


def build_report(df: pd.DataFrame, customer: str, as_of: datetime) -> str:
    df = df.copy()
    df["Inv Date"] = pd.to_datetime(df["Inv Date"], errors="coerce")
    df["FY"] = df["Inv Date"].apply(fy_label)
    df["CY"] = df["Inv Date"].dt.year

    first_invoice = df["Inv Date"].min()
    lifetime_billing = int(df["Inv Value"].sum())
    outstanding_balance = int(df["Balance"].sum())
    order_count = df["Order No"].nunique()

    fy_breakdown = (
        df.dropna(subset=["FY"])
        .groupby("FY")
        .agg(total_value=("Inv Value", "sum"), invoice_count=("Inv No", "size"))
        .reset_index()
    )
    fy_breakdown["start_year"] = fy_breakdown["FY"].str.extract(r"FY(\d{4})")[0].astype(int)
    fy_breakdown = fy_breakdown.sort_values("start_year")

    current_year = as_of.year
    cy_current = df[df["CY"] == current_year]
    cy_value = int(cy_current["Inv Value"].sum()) if not cy_current.empty else 0
    cy_count = int(cy_current.shape[0]) if not cy_current.empty else 0

    undated = df[df["FY"].isna()]
    undated_value = int(undated["Inv Value"].sum())
    undated_count = int(undated.shape[0])

    lines = []
    lines.append(f"Customer Billing Summary — {customer} (as of {as_of:%d-%b-%Y})")
    lines.append("")
    lines.append("1) Lifetime billing")
    lines.append(f"   Total invoiced: Rs {lifetime_billing:,}")
    if pd.notna(first_invoice):
        lines.append(f"   First invoice date: {first_invoice:%d-%b-%Y}")
    lines.append("")
    lines.append("2) Billing by financial year (April–March)")
    for _, row in fy_breakdown.iterrows():
        lines.append(
            f"   {row['FY']}: Rs {int(row['total_value']):,} across {row['invoice_count']} invoice(s)"
        )
    if undated_count:
        lines.append(f"   Not dated: Rs {undated_value:,} across {undated_count} entry")
    lines.append("")
    lines.append(f"3) Billing for current calendar year (Jan–Dec {current_year})")
    lines.append(f"   {current_year}: Rs {cy_value:,} across {cy_count} invoice(s)")
    lines.append("")
    lines.append("4) Current outstanding balance")
    lines.append(f"   Rs {outstanding_balance:,}")
    lines.append("")
    lines.append("5) Total number of rented orders")
    lines.append(f"   {order_count}")

    return "\n".join(lines)


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a customer billing summary report.")
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
        help="Optional output path. Defaults to 'Customer Billing Summary - <customer> (as of <date>).txt' next to the input.",
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
    required_columns = {"Inv Date", "Inv Value", "Balance", "Order No", "Inv No"}
    missing = required_columns - set(df.columns)
    if missing:
        raise ValueError(f"Input missing required columns: {', '.join(sorted(missing))}")

    customer = args.customer
    if customer == "Customer":
        inferred = infer_customer_name(df)
        if inferred:
            customer = inferred

    report_text = build_report(df, customer, as_of)

    output_path = (
        Path(args.output)
        if args.output
        else input_path.with_name(
            f"Customer Billing Summary - {customer} (as of {as_of:%d-%b-%Y}).txt"
        )
    )
    output_path.write_text(report_text)
    print(f"Wrote report: {output_path}")


if __name__ == "__main__":
    main()
