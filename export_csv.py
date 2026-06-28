"""
Export all SQLite tables to separate CSV files.

Usage:
    python export_csv.py                  # writes to ./exports/
    python export_csv.py --out data/csv   # custom output folder
    python export_csv.py --db abi.db      # custom database path
"""

import argparse
import os
import sqlite3

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB = os.path.join(_HERE, "abi.db")
DEFAULT_OUT = os.path.join(_HERE, "exports")


def list_tables(conn: sqlite3.Connection) -> list[str]:
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return [row[0] for row in cur.fetchall()]


def export_all(db_path: str = DEFAULT_DB, out_dir: str = DEFAULT_OUT) -> dict[str, int]:
    """Export every table to {out_dir}/{table_name}.csv. Returns table -> row count."""
    os.makedirs(out_dir, exist_ok=True)

    conn = sqlite3.connect(db_path)
    tables = list_tables(conn)
    counts = {}

    for table in tables:
        df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
        out_path = os.path.join(out_dir, f"{table}.csv")
        df.to_csv(out_path, index=False, encoding="utf-8")
        counts[table] = len(df)
        print(f"  {table}.csv  ({len(df)} rows)")

    conn.close()
    return counts


def main():
    parser = argparse.ArgumentParser(description="Export abi.db tables to CSV files")
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to SQLite database")
    parser.add_argument("--out", default=DEFAULT_OUT, help="Output folder for CSV files")
    args = parser.parse_args()

    if not os.path.exists(args.db):
        print(f"Database not found: {args.db}")
        print("Run: python pipeline.py")
        raise SystemExit(1)

    print(f"Exporting {args.db} -> {args.out}/")
    counts = export_all(args.db, args.out)
    print(f"\nDone. {len(counts)} tables exported to {os.path.abspath(args.out)}")


if __name__ == "__main__":
    main()
