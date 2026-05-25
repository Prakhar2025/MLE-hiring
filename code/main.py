"""
main.py — Entry point. Reads support_tickets.csv, runs the agent on every row,
writes all 14 output columns to support_tickets/output.csv.

Usage:
    # From repo root (activate venv first):
    python code/main.py

    # Or with explicit paths:
    python code/main.py --input support_tickets/support_tickets.csv --output support_tickets/output.csv
"""

import sys
import os
import argparse
import csv
from pathlib import Path

# Ensure code/ is on the path so imports work regardless of CWD
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

import pandas as pd
from tqdm import tqdm

from agent import SupportAgent
from schemas import CSV_COLUMNS
from config import INPUT_CSV, OUTPUT_CSV


def parse_args():
    parser = argparse.ArgumentParser(description="MLE Hiring Challenge — Support Triage Agent")
    parser.add_argument("--input",  default=str(INPUT_CSV),  help="Path to input CSV")
    parser.add_argument("--output", default=str(OUTPUT_CSV), help="Path to output CSV")
    return parser.parse_args()


def main():
    args = parse_args()
    input_path  = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        sys.exit(1)

    # Load tickets
    df = pd.read_csv(input_path, dtype=str, keep_default_na=False)
    print(f"[Main] Loaded {len(df)} tickets from {input_path}")

    # Normalise column names to lowercase
    df.columns = [c.strip().lower() for c in df.columns]
    required_cols = {"issue", "subject", "company"}
    missing = required_cols - set(df.columns)
    if missing:
        print(f"ERROR: Input CSV missing columns: {missing}")
        sys.exit(1)

    # Initialise agent (builds BM25 index once)
    agent = SupportAgent()

    # Process tickets
    rows = []
    for idx, row in tqdm(df.iterrows(), total=len(df), desc="Processing tickets"):
        issue   = str(row.get("issue",   "")).strip()
        subject = str(row.get("subject", "")).strip()
        company = str(row.get("company", "")).strip()

        result = agent.process(issue, subject, company)
        rows.append(result.to_csv_row())

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)

    print(f"[Main] Done. Output written to {output_path} ({len(rows)} rows)")
    print("[Main] Run 'python code/validate_output.py' to verify format.")


if __name__ == "__main__":
    main()
