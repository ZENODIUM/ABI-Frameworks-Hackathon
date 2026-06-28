"""
Determine Medicare Part B eligibility and assign routing decisions for each patient.

Routing logic:
  1. No active Medicare Part B coverage → reject
  2. No wound-related active diagnosis AND no wound extracted from notes/assessments → reject
  3. All required fields present (wound_type, length, width, depth, drainage) → auto_accept
  4. Some fields missing → flag_for_review
  5. Wound documented but no measurements extractable → flag_for_review
"""

import sqlite3
import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)

DB_PATH = "abi.db"

# ICD-10 prefixes / keywords that indicate a wound condition
WOUND_ICD_PREFIXES = ("L89", "L97", "L98", "I83", "T79", "T81")
WOUND_ICD_KEYWORDS = (
    "ulcer", "wound", "abscess", "burn", "pressure", "diabetic foot",
    "venous", "arterial", "sore", "skin breakdown"
)

REQUIRED_FIELDS_ALL = ("wound_type", "location", "length_cm", "width_cm", "depth_cm", "drainage_amount")
MEASURE_MISMATCH_TOLERANCE_CM = 0.5

FIELD_LABELS = {
    "wound_type": "wound type",
    "location": "location",
    "stage": "stage",
    "length_cm": "length",
    "width_cm": "width",
    "depth_cm": "depth",
    "drainage_amount": "drainage level",
}


def is_pressure_ulcer(wound_type: str | None) -> bool:
    if not wound_type:
        return False
    return "pressure" in str(wound_type).lower()


def get_required_fields(wound_data: dict) -> tuple[str, ...]:
    """Stage is required only for pressure ulcers."""
    fields = list(REQUIRED_FIELDS_ALL)
    if is_pressure_ulcer(wound_data.get("wound_type")):
        fields.append("stage")
    return tuple(fields)


def get_missing_fields(wound_data: dict) -> list[str]:
    return [f for f in get_required_fields(wound_data) if not wound_data.get(f)]


# ---------------------------------------------------------------------------
# Coverage check
# ---------------------------------------------------------------------------

def has_active_medicare_b(coverage_rows: list) -> tuple[bool, str]:
    """
    Returns (True, reason) if patient has active Medicare Part B coverage.
    Active = payer_code MCB and effective_to is null or in the future.
    """
    today = datetime.now(timezone.utc).date()
    for row in coverage_rows:
        if (row.get("payer_code") or "").upper() != "MCB":
            continue
        eff_to = row.get("effective_to")
        if eff_to is None:
            return True, "Active Medicare Part B (no end date)"
        try:
            end_date = datetime.fromisoformat(str(eff_to).replace("Z", "+00:00")).date()
            if end_date >= today:
                return True, f"Active Medicare Part B (ends {end_date})"
        except ValueError:
            return True, "Active Medicare Part B"
    return False, "No active Medicare Part B coverage found"


# ---------------------------------------------------------------------------
# Diagnosis check
# ---------------------------------------------------------------------------

def has_wound_diagnosis(diagnosis_rows: list) -> tuple[bool, str]:
    """
    Returns (True, code+description) if any active diagnosis is wound-related.
    """
    for row in diagnosis_rows:
        if (row.get("clinical_status") or "").lower() not in ("active", ""):
            continue
        code = (row.get("icd10_code") or "").upper()
        desc = (row.get("icd10_description") or "").lower()

        if any(code.startswith(pfx) for pfx in WOUND_ICD_PREFIXES):
            return True, f"{code} — {row.get('icd10_description')}"
        if any(kw in desc for kw in WOUND_ICD_KEYWORDS):
            return True, f"{code} — {row.get('icd10_description')}"

    return False, "No wound-related active diagnosis"


def has_only_resolved_wound_diagnosis(diagnosis_rows: list) -> bool:
    """True if wound-related diagnoses exist but none are active."""
    found_wound = False
    for row in diagnosis_rows:
        code = (row.get("icd10_code") or "").upper()
        desc = (row.get("icd10_description") or "").lower()
        status = (row.get("clinical_status") or "").lower()

        is_wound = (
            any(code.startswith(pfx) for pfx in WOUND_ICD_PREFIXES)
            or any(kw in desc for kw in WOUND_ICD_KEYWORDS)
        )
        if not is_wound:
            continue
        found_wound = True
        if status in ("active", ""):
            return False
    return found_wound


# ---------------------------------------------------------------------------
# Cross-source validation (ambiguity / anomaly checks)
# ---------------------------------------------------------------------------

def _floats_differ(a, b, tolerance: float = MEASURE_MISMATCH_TOLERANCE_CM) -> bool:
    try:
        return abs(float(a) - float(b)) > tolerance
    except (TypeError, ValueError):
        return False


def detect_ambiguities(
    primary_payer_code: str | None,
    coverage_rows: list,
    has_mcb: bool,
    has_dx: bool,
    wound_data: dict,
) -> list[str]:
    """
    Return human-readable ambiguity flags when sources disagree or look suspicious.
    Missing fields alone are handled separately — these are consistency checks.
    """
    flags = []

    # Primary payer on patient record vs coverage table
    if primary_payer_code == "MCB" and not has_mcb:
        flags.append("patient record shows Medicare B as primary payer but no active MCB in coverage")
    elif primary_payer_code and primary_payer_code != "MCB" and has_mcb:
        flags.append("active Medicare B in coverage but primary payer on record is not MCB")

    # Expired MCB explicitly listed (informational — has_mcb would already be False)
    for row in coverage_rows:
        if (row.get("payer_code") or "").upper() == "MCB" and row.get("effective_to"):
            flags.append("Medicare B coverage has an end date — verify still billable")

    assess = wound_data.get("_assessment_fields") or {}
    notes = wound_data.get("_note_fields") or {}

    # Note vs assessment measurement mismatch (only when both sources have the field)
    for field, label in (("length_cm", "length"), ("width_cm", "width"), ("depth_cm", "depth")):
        av, nv = assess.get(field), notes.get(field)
        if av is not None and nv is not None and _floats_differ(av, nv):
            flags.append(f"note vs assessment {label} mismatch ({nv} vs {av} cm)")

    # Diagnosis says wound but nothing extractable from notes/assessments
    if has_dx and wound_data.get("extraction_source") == "none":
        flags.append("wound ICD-10 on file but no wound details found in notes or assessments")

    # Wound documented clinically but no formal wound diagnosis
    if not has_dx and wound_data.get("wound_type"):
        flags.append("wound documented in notes/assessment but no active wound ICD-10 diagnosis")

    # Anatomically suspicious measurements
    length = wound_data.get("length_cm")
    depth = wound_data.get("depth_cm")
    if length is not None and depth is not None:
        try:
            if float(depth) > float(length):
                flags.append(f"depth ({depth} cm) exceeds length ({length} cm) — verify measurements")
        except (TypeError, ValueError):
            pass

    return flags


# ---------------------------------------------------------------------------
# Routing decision
# ---------------------------------------------------------------------------

def make_routing_decision(
    coverage_rows: list,
    diagnosis_rows: list,
    wound_data: dict,
    primary_payer_code: str | None = None,
) -> dict:
    """
    Returns dict with:
      routing        : 'auto_accept' | 'flag_for_review' | 'reject'
      reason         : plain-English explanation for the biller
      has_medicare_b : bool
      has_wound_dx   : bool
    """
    has_mcb, mcb_reason = has_active_medicare_b(coverage_rows)
    has_dx, dx_reason = has_wound_diagnosis(diagnosis_rows)
    resolved_only = has_only_resolved_wound_diagnosis(diagnosis_rows)
    ambiguities = detect_ambiguities(
        primary_payer_code, coverage_rows, has_mcb, has_dx, wound_data
    )

    extraction_source = wound_data.get("extraction_source", "none")
    has_wound_data = extraction_source != "none"
    wound_type = wound_data.get("wound_type")

    # Step 1 — must have Medicare Part B
    if not has_mcb:
        return {
            "routing": "reject",
            "reason": f"Rejected: {mcb_reason}",
            "has_medicare_b": False,
            "has_wound_dx": has_dx,
            "ambiguity_flags": "",
        }

    # Step 2 — wound diagnosis resolved (no active wound ICD-10)
    if resolved_only:
        return {
            "routing": "reject",
            "reason": "Rejected: wound diagnosis is resolved/inactive — not billable",
            "has_medicare_b": True,
            "has_wound_dx": False,
            "ambiguity_flags": "",
        }

    # Step 3 — must have wound evidence (active diagnosis or clinical documentation)
    if not has_dx and not has_wound_data:
        return {
            "routing": "reject",
            "reason": "Rejected: No active wound diagnosis and no wound documented in notes/assessments",
            "has_medicare_b": True,
            "has_wound_dx": False,
            "ambiguity_flags": "",
        }

    # Step 4 — completeness: type, location, L/W/D, drainage; stage if pressure ulcer
    missing = get_missing_fields(wound_data)

    if not missing and not ambiguities:
        stage_note = f", stage {wound_data.get('stage')}" if is_pressure_ulcer(wound_type) else ""
        return {
            "routing": "auto_accept",
            "reason": (
                f"All required fields documented. "
                f"Wound: {wound_type.replace('_', ' ') if wound_type else 'documented'} "
                f"at {wound_data.get('location')}{stage_note}, "
                f"{wound_data.get('length_cm')}x{wound_data.get('width_cm')}x{wound_data.get('depth_cm')} cm, "
                f"drainage: {wound_data.get('drainage_amount')}. "
                f"Medicare Part B active. Sources consistent."
            ),
            "has_medicare_b": True,
            "has_wound_dx": has_dx,
            "ambiguity_flags": "",
        }

    # Step 5 — incomplete or ambiguous → flag
    reason_parts = []
    if missing:
        missing_readable = ", ".join(FIELD_LABELS[f] for f in missing)
        reason_parts.append(f"missing: {missing_readable}")
    if ambiguities:
        reason_parts.append("concerns: " + "; ".join(ambiguities))

    if wound_type or has_dx or has_wound_data:
        return {
            "routing": "flag_for_review",
            "reason": (
                f"Flagged: wound documented"
                f"{' (' + str(wound_type).replace('_', ' ') + ')' if wound_type else ''}"
                f" — {'; '.join(reason_parts)}. "
                f"Medicare Part B active. Manual review needed."
            ),
            "has_medicare_b": True,
            "has_wound_dx": has_dx,
            "ambiguity_flags": "; ".join(ambiguities),
        }

    return {
        "routing": "reject",
        "reason": "Rejected: reliable extraction not possible — insufficient clinical documentation",
        "has_medicare_b": True,
        "has_wound_dx": has_dx,
        "ambiguity_flags": "",
    }


# ---------------------------------------------------------------------------
# Build full output rows
# ---------------------------------------------------------------------------

def build_output(conn: sqlite3.Connection, wound_extractions: dict) -> list[dict]:
    """
    For each patient, combine all data sources and produce one output row.
    wound_extractions: {patient_id_str -> wound fields dict}
    """
    cur = conn.cursor()
    cur.execute("SELECT id, facility_id, patient_id, first_name, last_name, primary_payer_code FROM patients")
    patients = cur.fetchall()

    rows = []
    for internal_id, facility_id, patient_id, first_name, last_name, payer_code in patients:

        # Coverage
        cur.execute(
            "SELECT payer_name, payer_code, payer_type, effective_from, effective_to FROM coverage WHERE patient_id=?",
            (patient_id,)
        )
        cov_rows = [dict(zip(["payer_name","payer_code","payer_type","effective_from","effective_to"], r))
                    for r in cur.fetchall()]

        # Diagnoses
        cur.execute(
            "SELECT icd10_code, icd10_description, clinical_status FROM diagnoses WHERE patient_id=?",
            (patient_id,)
        )
        dx_rows = [dict(zip(["icd10_code","icd10_description","clinical_status"], r))
                   for r in cur.fetchall()]

        wound_data = wound_extractions.get(patient_id, {"extraction_source": "none"})

        decision = make_routing_decision(cov_rows, dx_rows, wound_data, payer_code)

        wound_dx_codes = ", ".join(
            r["icd10_code"] for r in dx_rows
            if (r.get("clinical_status") or "").lower() in ("active", "")
            and r.get("icd10_code")
        )

        rows.append({
            "patient_id": patient_id,
            "facility_id": facility_id,
            "name": f"{first_name or ''} {last_name or ''}".strip(),
            "primary_payer": payer_code,
            "has_medicare_b": decision["has_medicare_b"],
            "has_wound_dx": decision["has_wound_dx"],
            "wound_dx_codes": wound_dx_codes,
            "wound_type": wound_data.get("wound_type", ""),
            "stage": wound_data.get("stage", ""),
            "location": wound_data.get("location", ""),
            "length_cm": wound_data.get("length_cm", ""),
            "width_cm": wound_data.get("width_cm", ""),
            "depth_cm": wound_data.get("depth_cm", ""),
            "drainage_amount": wound_data.get("drainage_amount", ""),
            "extraction_source": wound_data.get("extraction_source", "none"),
            "routing": decision["routing"],
            "reason": decision["reason"],
            "ambiguity_flags": decision.get("ambiguity_flags", ""),
        })

    return rows


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import json
    conn = sqlite3.connect(DB_PATH)
    # Quick test with a single patient to verify logic
    cur = conn.cursor()
    cur.execute("SELECT patient_id FROM patients LIMIT 5")
    for (pid,) in cur.fetchall():
        print(f"\n--- {pid} ---")
        cur2 = conn.cursor()
        cur2.execute("SELECT payer_code, effective_to FROM coverage WHERE patient_id=?", (pid,))
        cov = [dict(zip(["payer_code","effective_to"], r)) for r in cur2.fetchall()]
        print("Coverage:", cov)
    conn.close()
