"""
Export pipeline output to JSON for the React dashboard.
Run after pipeline: python export_dashboard_data.py
"""

import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "abi.db"
OUT_PATH = ROOT / "dashboard" / "public" / "patients.json"
META_PATH = ROOT / "dashboard" / "public" / "meta.json"

FACILITY_LABELS = {101: "Facility A", 102: "Facility B", 103: "Facility C"}
ROUTING_LABELS = {
    "auto_accept": "Auto Accept",
    "flag_for_review": "Flag for Review",
    "reject": "Reject",
}


def _fmt_measure(val):
    if val is None or val == "":
        return None
    try:
        n = float(val)
        if n == int(n):
            return str(int(n))
        return f"{n:g}"
    except (TypeError, ValueError):
        return val


def _parse_missing(reason: str) -> list[str]:
    m = re.search(r"missing:\s*([^.]+)", reason or "", re.I)
    if not m:
        return []
    return [f.strip() for f in m.group(1).split(",") if f.strip()]


def _reject_category(reason: str) -> str | None:
    r = (reason or "").lower()
    if "medicare part b" in r or "no active medicare" in r:
        return "no_medicare_b"
    if "resolved" in r or "inactive" in r:
        return "resolved_diagnosis"
    if "no active wound" in r or "no wound" in r:
        return "no_wound_evidence"
    return "other_reject"


def _ambiguity_types(flags: str) -> list[str]:
    if not flags:
        return []
    types = []
    f = flags.lower()
    if "mismatch" in f:
        types.append("source_mismatch")
    if "exceeds length" in f:
        types.append("depth_exceeds_length")
    if "primary payer" in f or "payer" in f:
        types.append("payer_mismatch")
    if "end date" in f:
        types.append("expired_mcb")
    if "icd-10" in f and "no wound details" in f:
        types.append("dx_without_docs")
    if "no active wound icd" in f or "no wound icd" in f:
        types.append("docs_without_dx")
    if not types:
        types.append("other_ambiguity")
    return types


def export():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM eligibility_output ORDER BY patient_id")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    patients = []
    for row in rows:
        reason = row.get("reason") or ""
        amb = row.get("ambiguity_flags") or ""
        routing = row.get("routing") or ""
        missing = _parse_missing(reason) if routing == "flag_for_review" else []

        patients.append({
            "patient_id": row.get("patient_id"),
            "facility_id": row.get("facility_id"),
            "facility": FACILITY_LABELS.get(row.get("facility_id"), str(row.get("facility_id"))),
            "name": row.get("name"),
            "primary_payer": row.get("primary_payer"),
            "has_medicare_b": bool(row.get("has_medicare_b")),
            "has_wound_dx": bool(row.get("has_wound_dx")),
            "wound_dx_codes": row.get("wound_dx_codes"),
            "wound_type": row.get("wound_type"),
            "stage": row.get("stage"),
            "location": row.get("location"),
            "length_cm": _fmt_measure(row.get("length_cm")),
            "width_cm": _fmt_measure(row.get("width_cm")),
            "depth_cm": _fmt_measure(row.get("depth_cm")),
            "drainage_amount": row.get("drainage_amount"),
            "extraction_source": row.get("extraction_source"),
            "routing": routing,
            "routing_label": ROUTING_LABELS.get(routing, routing),
            "reason": reason,
            "ambiguity_flags": amb,
            "has_ambiguity": bool(amb.strip()),
            "missing_fields": missing,
            "reject_category": _reject_category(reason) if routing == "reject" else None,
            "ambiguity_types": _ambiguity_types(amb),
            "used_llm": "+llm" in str(row.get("extraction_source") or ""),
        })

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(patients, f, indent=2)

    counts = {
        "total": len(patients),
        "auto_accept": sum(1 for p in patients if p["routing"] == "auto_accept"),
        "flag_for_review": sum(1 for p in patients if p["routing"] == "flag_for_review"),
        "reject": sum(1 for p in patients if p["routing"] == "reject"),
        "medicare_b": sum(1 for p in patients if p["has_medicare_b"]),
    }
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(counts, f, indent=2)

    print(f"Exported {len(patients)} patients -> {OUT_PATH}")


if __name__ == "__main__":
    export()
