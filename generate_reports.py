#!/usr/bin/env python3
"""
Interactive entrypoint for generating PNZ reports.

Provides two flows:
  1) Customer Billing Summary (full billing view)
  2) Outstanding Balance Summary (balance-only view)

Supports CSV, XLS, XLSX, and ODS inputs (pandas must have the right extras installed
for Excel/ODS engines).
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from balance_sum_report import build_balance_report, infer_customer_name as infer_balance_name
from generate_billing_report import build_report as build_billing_report
from generate_billing_report import infer_customer_name as infer_billing_name


SUPPORTED_SUFFIXES = {".csv", ".xls", ".xlsx", ".ods"}


def list_candidate_files(folder: Path) -> list[Path]:
    """Return candidate input files in folder, newest first."""
    files: Iterable[Path] = folder.glob("*")
    candidates = [p for p in files if p.suffix.lower() in SUPPORTED_SUFFIXES and p.is_file()]
    return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)


def prompt_file(folder: Path) -> Optional[Path]:
    files = list_candidate_files(folder)
    if not files:
        print("No CSV/Excel/ODS files found in the current directory.", file=sys.stderr)
        return None

    print("Select an input file:")
    for idx, path in enumerate(files, start=1):
        mtime = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        print(f"  {idx}) {path.name} (modified {mtime})")
    print("  0) Enter a custom path")

    try:
        choice_raw = input("Enter choice: ").strip()
    except EOFError:
        return None

    try:
        choice = int(choice_raw)
    except ValueError:
        print("Invalid selection.", file=sys.stderr)
        return None

    if choice == 0:
        custom = input("Enter path: ").strip()
        return Path(custom) if custom else None
    if 1 <= choice <= len(files):
        return files[choice - 1]

    print("Selection out of range.", file=sys.stderr)
    return None


def load_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    # Let pandas pick the right engine for Excel/ODS
    return pd.read_excel(path)


def prompt_customer(inferred: Optional[str]) -> str:
    default_label = inferred or "Customer"
    entered = input(f"Customer name [{default_label}]: ").strip()
    return entered or default_label


def prompt_as_of() -> datetime:
    today_str = datetime.today().strftime("%Y-%m-%d")
    entered = input(f"As-of date (YYYY-MM-DD) [{today_str}]: ").strip()
    use_str = entered or today_str
    try:
        return datetime.strptime(use_str, "%Y-%m-%d")
    except ValueError:
        print("Invalid date format, using today instead.", file=sys.stderr)
        return datetime.today()


def run_billing_summary(input_path: Path) -> None:
    df = load_table(input_path)
    missing = {"Inv Date", "Inv Value", "Balance", "Order No", "Inv No"} - set(df.columns)
    if missing:
        raise ValueError(f"Input missing required columns: {', '.join(sorted(missing))}")

    inferred = infer_billing_name(df)
    customer = prompt_customer(inferred)
    as_of = prompt_as_of()

    report_text = build_billing_report(df, customer, as_of)
    output_path = input_path.with_name(f"Customer Billing Summary - {customer} (as of {as_of:%d-%b-%Y}).txt")
    output_path.write_text(report_text)
    print(f"Wrote billing summary: {output_path}")


def run_balance_summary(input_path: Path) -> None:
    df = load_table(input_path)
    if "Balance" not in df.columns:
        raise ValueError("Input missing required column: Balance")

    inferred = infer_balance_name(df)
    customer = prompt_customer(inferred)
    as_of = prompt_as_of()

    report_text = build_balance_report(df, customer, as_of)
    output_path = input_path.with_name(f"Balance Summary - {customer} (as of {as_of:%d-%b-%Y}).txt")
    output_path.write_text(report_text)
    print(f"Wrote balance summary: {output_path}")


def main() -> None:
    print("What would you like to generate?")
    print("  1) Customer Billing Summary (lifetime, FY/CY breakdown, outstanding, orders)")
    print("  2) Outstanding Balance Summary (balance-only view)")
    try:
        choice_raw = input("Enter choice (1/2): ").strip()
    except EOFError:
        return

    if choice_raw not in {"1", "2"}:
        print("Invalid choice. Exiting.", file=sys.stderr)
        return

    input_path = prompt_file(Path("."))
    if not input_path:
        print("No input file selected. Exiting.", file=sys.stderr)
        return
    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        return

    try:
        if choice_raw == "1":
            run_billing_summary(input_path)
        else:
            run_balance_summary(input_path)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
