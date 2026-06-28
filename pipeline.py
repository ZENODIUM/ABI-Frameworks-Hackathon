"""
Orchestrator: runs ingestion → extraction → eligibility → saves output.csv
Run this once to populate the database and produce the final output table.
"""

import sqlite3
import csv
import logging
import sys
import os
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("pipeline.log", encoding="utf-8", errors="replace"),
    ]
)
log = logging.getLogger(__name__)

DB_PATH = "abi.db"
OUTPUT_CSV = "output.csv"


def run():
    # ------------------------------------------------------------------
    # Step 1: Ingestion
    # ------------------------------------------------------------------
    skip_ingestion = os.path.exists(DB_PATH) and "--skip-ingest" in sys.argv
    incremental = "--incremental" in sys.argv

    if skip_ingestion:
        log.info("Skipping ingestion (--skip-ingest). Using existing database.")
        total = None
    else:
        log.info("=" * 60)
        if incremental:
            log.info("STEP 1: Incremental sync (only modified records)...")
        else:
            log.info("STEP 1: Full ingest from PCC API...")
        log.info("=" * 60)
        from ingestion import ingest_all
        total, mode = ingest_all(incremental=incremental)
        log.info("Sync complete. Mode=%s, patients=%s", mode, total)

    # ------------------------------------------------------------------
    # Step 2: Extraction
    # ------------------------------------------------------------------
    log.info("=" * 60)
    log.info("STEP 2: Extracting wound data from notes and assessments...")
    log.info("=" * 60)
    from extraction import run_extraction
    wound_extractions = run_extraction(DB_PATH)

    found_wounds = sum(1 for v in wound_extractions.values() if v.get("wound_type"))
    log.info("Wound type extracted for %d / %d patients", found_wounds, len(wound_extractions))

    # Optional LLM gap-fill for patients still missing required fields
    if "--use-llm" in sys.argv:
        log.info("=" * 60)
        log.info("STEP 2b: LLM gap-fill (Gemini) for incomplete extractions...")
        log.info("=" * 60)
        try:
            from llm_extraction import fill_gaps_with_llm
            wound_extractions = fill_gaps_with_llm(DB_PATH, wound_extractions)
        except RuntimeError as e:
            log.warning("LLM skipped: %s", e)

    # ------------------------------------------------------------------
    # Step 3: Eligibility + routing decisions
    # ------------------------------------------------------------------
    log.info("=" * 60)
    log.info("STEP 3: Running eligibility and routing decisions...")
    log.info("=" * 60)
    from eligibility import build_output
    conn = sqlite3.connect(DB_PATH)
    output_rows = build_output(conn, wound_extractions)
    conn.close()

    # ------------------------------------------------------------------
    # Step 4: Save output
    # ------------------------------------------------------------------
    log.info("=" * 60)
    log.info("STEP 4: Saving output...")
    log.info("=" * 60)

    # Save to CSV
    if output_rows:
        fieldnames = list(output_rows[0].keys())
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(output_rows)
        log.info("Saved %d rows to %s", len(output_rows), OUTPUT_CSV)

    # Save to SQLite output table
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS eligibility_output")
    cur.execute("""
        CREATE TABLE eligibility_output (
            patient_id TEXT PRIMARY KEY,
            facility_id INTEGER,
            name TEXT,
            primary_payer TEXT,
            has_medicare_b INTEGER,
            has_wound_dx INTEGER,
            wound_dx_codes TEXT,
            wound_type TEXT,
            stage TEXT,
            location TEXT,
            length_cm REAL,
            width_cm REAL,
            depth_cm REAL,
            drainage_amount TEXT,
            extraction_source TEXT,
            routing TEXT,
            reason TEXT,
            ambiguity_flags TEXT
        )
    """)
    for row in output_rows:
        cur.execute("""
            INSERT OR REPLACE INTO eligibility_output VALUES
            (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            row["patient_id"], row["facility_id"], row["name"],
            row["primary_payer"],
            int(row["has_medicare_b"]), int(row["has_wound_dx"]),
            row["wound_dx_codes"], row["wound_type"], str(row.get("stage", "")),
            row["location"], row["length_cm"] or None, row["width_cm"] or None,
            row["depth_cm"] or None, row["drainage_amount"],
            row["extraction_source"], row["routing"], row["reason"],
            row.get("ambiguity_flags", ""),
        ))
    conn.commit()
    conn.close()

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    log.info("=" * 60)
    log.info("PIPELINE COMPLETE")
    log.info("=" * 60)

    routing_counts = {}
    for row in output_rows:
        r = row["routing"]
        routing_counts[r] = routing_counts.get(r, 0) + 1

    log.info("Total patients processed : %d", len(output_rows))
    log.info("  auto_accept            : %d", routing_counts.get("auto_accept", 0))
    log.info("  flag_for_review        : %d", routing_counts.get("flag_for_review", 0))
    log.info("  reject                 : %d", routing_counts.get("reject", 0))
    log.info("")
    log.info("Output saved to: %s", OUTPUT_CSV)
    log.info("Launch dashboard: streamlit run app.py")

    return output_rows


if __name__ == "__main__":
    run()
