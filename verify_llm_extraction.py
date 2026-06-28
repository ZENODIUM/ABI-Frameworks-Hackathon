"""
Verify that fields filled by Gemini are supported by source clinical data.

Compares regex-only extraction against post-LLM extraction (or eligibility_output
from the last pipeline run), then checks each LLM-filled value against the
patient's diagnoses, assessments, and notes in abi.db.

Usage:
    python verify_llm_extraction.py
        # diff regex vs eligibility_output; verify patients with +llm in source

    python verify_llm_extraction.py --use-llm
        # re-run Gemini gap-fill (needs GEMINI_API_KEY), then verify

    python verify_llm_extraction.py --export
        # also write exports/llm_verification_report.csv

A field is considered verified when its value (or an equivalent form) appears
in the patient's raw diagnoses, assessment JSON, or note text.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "abi.db"
EXPORT_PATH = Path(__file__).resolve().parent / "exports" / "llm_verification_report.csv"

WOUND_FIELDS = (
    "wound_type",
    "stage",
    "location",
    "length_cm",
    "width_cm",
    "depth_cm",
    "drainage_amount",
)

DRAINAGE_ALIASES = {
    "none": ("none", "no drainage", "dry"),
    "light": ("light", "scant", "minimal", "small", "serous"),
    "moderate": ("moderate", "mod", "serosanguineous"),
    "heavy": ("heavy", "large", "copious", "purulent"),
}

WOUND_TYPE_ALIASES = {
    "pressure_ulcer": ("pressure ulcer", "pressure injury", "pressure sore"),
    "diabetic": ("diabetic", "dfu", "diabetic foot"),
    "diabetic_foot_ulcer": ("diabetic foot ulcer", "dfu"),
    "venous": ("venous", "venous stasis"),
    "arterial": ("arterial", "arterial ulcer"),
    "surgical": ("surgical", "surgical site", "ssi"),
    "abscess": ("abscess",),
    "burn": ("burn",),
}


def _is_empty(val) -> bool:
    return val is None or val == ""


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).lower().strip())


def gather_source_text(conn: sqlite3.Connection, patient_id: str, internal_id: int) -> str:
    """Full clinical source text for verification (not truncated)."""
    cur = conn.cursor()
    parts: list[str] = []

    for code, desc, status in cur.execute(
        "SELECT icd10_code, icd10_description, clinical_status "
        "FROM diagnoses WHERE patient_id=?",
        (patient_id,),
    ):
        parts.append(f"{code} {status} {desc}")

    for _atype, _adate, raw in cur.execute(
        "SELECT assessment_type, assessment_date, raw_json FROM assessments "
        "WHERE patient_id=? AND is_current=1",
        (internal_id,),
    ):
        parts.append(raw or "")

    for _ntype, _edate, text in cur.execute(
        "SELECT note_type, effective_date, note_text FROM notes "
        "WHERE patient_id=? AND is_current=1 ORDER BY effective_date",
        (internal_id,),
    ):
        parts.append(text or "")

    return "\n".join(parts)


def _number_variants(num: float) -> list[str]:
    """Common string forms of a measurement in clinical text."""
    variants = {str(num), f"{num:.1f}", f"{num:.2f}"}
    if num == int(num):
        variants.add(str(int(num)))
    return list(variants)


def verify_field(field: str, value, source_text: str) -> tuple[bool, str]:
    """
    Return (verified, detail) — whether value is supported by source_text.
    """
    if _is_empty(value):
        return False, "empty value"

    src = _normalize(source_text)
    src_compact = re.sub(r"[^a-z0-9.]+", "", src)

    if field == "location":
        loc = _normalize(str(value).replace("_", " "))
        if loc in src:
            return True, "verbatim in source"
        words = [w for w in loc.split() if len(w) > 3]
        if len(words) >= 2 and all(w in src for w in words):
            return True, "all significant location words present"
        # Abbreviated notes e.g. "rightlowerex" for "right lower extremity"
        compact = re.sub(r"[^a-z0-9]+", "", loc)
        if compact and compact in src_compact:
            return True, "compact location form in source"
        return False, "location not found in diagnoses/assessments/notes"

    if field == "stage":
        stage = str(value).lower()
        if stage in ("unstageable", "un-stageable"):
            if "unstageable" in src or "un-stageable" in src:
                return True, "unstageable documented in source"
            return False, "unstageable not found in source"
        stage_patterns = (
            f"stage {stage}",
            f"stage {stage} ",
            f"stage: stage {stage}",
        )
        if any(p in src for p in stage_patterns):
            return True, f"stage {stage} in clinical text"
        # ICD descriptions e.g. "Stage 3 Pressure Ulcer"
        if re.search(rf"stage\s*{re.escape(stage)}\b", src):
            return True, f"stage {stage} in ICD or narrative"
        return False, f"stage {stage} not found in source"

    if field in ("length_cm", "width_cm", "depth_cm"):
        try:
            num = float(value)
        except (TypeError, ValueError):
            return False, "non-numeric measurement"
        for variant in _number_variants(num):
            if variant in src or variant in source_text:
                return True, f"measurement {variant} found in source"
        return False, f"measurement {value} not found in source"

    if field == "drainage_amount":
        level = _normalize(str(value))
        aliases = DRAINAGE_ALIASES.get(level, (level,))
        for alias in aliases:
            if alias in src:
                return True, f"drainage '{alias}' found in source"
        return False, f"drainage level '{level}' not found in source"

    if field == "wound_type":
        wtype = _normalize(str(value).replace("_", " "))
        aliases = WOUND_TYPE_ALIASES.get(str(value).lower(), (wtype,))
        for alias in aliases:
            if alias in src:
                return True, f"wound type '{alias}' found in source"
        if wtype in src:
            return True, f"wound type '{wtype}' found in source"
        return False, f"wound type '{wtype}' not found in source"

    return False, f"unsupported field '{field}'"


def find_llm_filled_fields(before: dict, after: dict) -> list[tuple[str, object]]:
    """Fields empty before LLM but populated after."""
    filled = []
    for field in WOUND_FIELDS:
        if _is_empty(before.get(field)) and not _is_empty(after.get(field)):
            filled.append((field, after.get(field)))
    return filled


def load_eligibility_extractions(conn: sqlite3.Connection) -> dict[str, dict]:
    cur = conn.cursor()
    cur.execute(
        "SELECT patient_id, wound_type, stage, location, length_cm, width_cm, "
        "depth_cm, drainage_amount, extraction_source FROM eligibility_output"
    )
    cols = [
        "wound_type", "stage", "location", "length_cm",
        "width_cm", "depth_cm", "drainage_amount", "extraction_source",
    ]
    out = {}
    for row in cur.fetchall():
        pid, *vals = row
        out[pid] = dict(zip(cols, vals))
    return out


def run_verification(use_llm: bool = False, export: bool = False) -> list[dict]:
    from extraction import run_extraction

    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, patient_id FROM patients")
    id_map = {pid: iid for iid, pid in cur.fetchall()}

    regex_ext = run_extraction(str(DB_PATH))

    if use_llm:
        from llm_extraction import fill_gaps_with_llm
        final_ext = fill_gaps_with_llm(str(DB_PATH), dict(regex_ext))
        compare_label = "regex vs live Gemini run"
    else:
        try:
            final_ext = load_eligibility_extractions(conn)
        except sqlite3.OperationalError:
            print(
                "eligibility_output table missing — run pipeline first "
                "or pass --use-llm",
                file=sys.stderr,
            )
            sys.exit(1)
        compare_label = "regex vs eligibility_output (last pipeline)"

    rows: list[dict] = []
    patients_with_llm = 0
    fields_checked = 0
    fields_verified = 0
    fields_failed = 0

    print("=" * 72)
    print("LLM FIELD VERIFICATION")
    print(f"Mode: {compare_label}")
    print("=" * 72)

    for pid in sorted(regex_ext):
        before = regex_ext[pid]
        after = final_ext.get(pid, {})
        source = after.get("extraction_source") or before.get("extraction_source") or ""

        if not use_llm and "+llm" not in str(source):
            continue

        llm_fields = find_llm_filled_fields(before, after)
        if not llm_fields and use_llm:
            # Live run may not change anything for this patient
            continue
        if not llm_fields:
            continue

        patients_with_llm += 1
        source_text = gather_source_text(conn, pid, id_map[pid])

        print(f"\n{pid}  (extraction_source: {source or 'n/a'})")
        for field, value in llm_fields:
            fields_checked += 1
            ok, detail = verify_field(field, value, source_text)
            status = "VERIFIED" if ok else "SUSPICIOUS"
            if ok:
                fields_verified += 1
            else:
                fields_failed += 1
            print(f"  {status:<11} {field}={value!r}  — {detail}")
            rows.append({
                "patient_id": pid,
                "field": field,
                "llm_value": value,
                "status": status,
                "detail": detail,
                "extraction_source": source,
            })

    conn.close()

    print("\n" + "=" * 72)
    print("SUMMARY")
    print("=" * 72)
    print(f"  Patients with LLM-filled fields : {patients_with_llm}")
    print(f"  Fields checked                  : {fields_checked}")
    print(f"  Verified in source              : {fields_verified}")
    print(f"  Suspicious / not found          : {fields_failed}")
    if fields_checked:
        pct = 100.0 * fields_verified / fields_checked
        print(f"  Verification rate               : {pct:.1f}%")

    if export and rows:
        EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(EXPORT_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "patient_id", "field", "llm_value", "status",
                    "detail", "extraction_source",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nReport written to {EXPORT_PATH}")

    return rows


def main():
    parser = argparse.ArgumentParser(
        description="Verify Gemini-filled wound fields against source clinical data.",
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Re-run Gemini gap-fill before verifying (needs GEMINI_API_KEY).",
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="Write exports/llm_verification_report.csv",
    )
    args = parser.parse_args()
    run_verification(use_llm=args.use_llm, export=args.export)


if __name__ == "__main__":
    main()
