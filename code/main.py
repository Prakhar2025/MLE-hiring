"""
main.py — Entry point. Reads support_tickets.csv, runs the agent on every row,
writes all 14 output columns to support_tickets/output.csv.

Uses ThreadPoolExecutor for parallel LLM calls to stay within the 3-minute
evaluation time limit. Results are collected in original order (deterministic).

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
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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

MAX_WORKERS = 8   # parallel LLM calls — safe for Groq rate limits


def parse_args():
    parser = argparse.ArgumentParser(description="MLE Hiring Challenge — Support Triage Agent")
    parser.add_argument("--input",   default=str(INPUT_CSV),  help="Path to input CSV")
    parser.add_argument("--output",  default=str(OUTPUT_CSV), help="Path to output CSV")
    parser.add_argument("--workers", default=MAX_WORKERS, type=int, help="Parallel workers")
    return parser.parse_args()


def process_one(agent: SupportAgent, idx: int, issue: str, subject: str, company: str):
    """Process a single ticket. Returns (idx, csv_row_dict)."""
    result = agent.process(issue, subject, company)
    return idx, result.to_csv_row()


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

    # Build agent once (BM25 index), shared across threads (read-only after init)
    agent = SupportAgent()

    start = time.time()
    rows_by_idx = {}

    print(f"[Main] Processing {len(df)} tickets with {args.workers} workers...")
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                process_one, agent,
                int(idx),
                str(row.get("issue",   "")).strip(),
                str(row.get("subject", "")).strip(),
                str(row.get("company", "")).strip(),
            ): int(idx)
            for idx, row in df.iterrows()
        }

        with tqdm(total=len(futures), desc="Processing tickets") as pbar:
            for future in as_completed(futures):
                idx, csv_row = future.result()
                rows_by_idx[idx] = csv_row
                pbar.update(1)

    elapsed = time.time() - start
    print(f"[Main] All tickets processed in {elapsed:.1f}s")

    # Restore original row order
    rows = [rows_by_idx[i] for i in sorted(rows_by_idx.keys())]

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)

    print(f"[Main] Done. Output written to {output_path} ({len(rows)} rows)")
    if elapsed > 180:
        print(f"[Main] WARNING: Took {elapsed:.0f}s — over 3-min limit! Reduce workers or tokens.")
    else:
        print(f"[Main] Time OK: {elapsed:.0f}s / 180s limit.")
    print("[Main] Run 'python code/validate_output.py' to verify format.")


if __name__ == "__main__":
    main()

