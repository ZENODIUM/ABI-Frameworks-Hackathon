"""
Extract wound fields from assessments (structured JSON) and progress notes (regex).
Priority: assessments > notes (assessments are pre-structured forms).
"""

import json
import re
import sqlite3
import logging

log = logging.getLogger(__name__)

DB_PATH = "abi.db"

# ---------------------------------------------------------------------------
# Regex patterns for note text
# ---------------------------------------------------------------------------

# Measurements: "3.2 x 2.1 x 0.4 cm" or "3.2x2.1x0.4cm"
MEAS_3D_END = re.compile(
    r"(\d+\.?\d*)\s*[xX×*]\s*(\d+\.?\d*)\s*[xX×*]\s*(\d+\.?\d*)\s*cm",
    re.IGNORECASE
)
# "4.3 cm x 1.8 cm x 0.3 cm" — cm after each number (IDT/Envive 3D)
MEAS_3D_EACH = re.compile(
    r"(\d+\.?\d*)\s*cm\s*[xX×]\s*(\d+\.?\d*)\s*cm\s*[xX×]\s*(\d+\.?\d*)\s*cm",
    re.IGNORECASE
)
# "2.9 cm x 2.8 cm" — 2D only (Envive Care Conference format, no depth)
MEAS_2D_EACH = re.compile(
    r"(\d+\.?\d*)\s*cm\s*[xX×]\s*(\d+\.?\d*)\s*cm",
    re.IGNORECASE
)
# "5.9 x 4.5cm" — 2D without cm-per-number (prose format)
MEAS_2D_END = re.compile(
    r"(\d+\.?\d*)\s*[xX×]\s*(\d+\.?\d*)\s*cm",
    re.IGNORECASE
)

# Individual labeled dimensions
LEN_PATTERN = re.compile(r"length[:\s]+(\d+\.?\d*)\s*cm?", re.IGNORECASE)
WID_PATTERN = re.compile(r"width[:\s]+(\d+\.?\d*)\s*cm?", re.IGNORECASE)
DEP_PATTERN = re.compile(r"depth[:\s]+(\d+\.?\d*)\s*cm?", re.IGNORECASE)
# "depth 1.8cm" or "1.8cm deep" (prose depth without colon)
DEP_PROSE   = re.compile(r"depth\s+(\d+\.?\d*)\s*cm|(\d+\.?\d*)\s*cm\s+deep", re.IGNORECASE)

# Drainage
DRAINAGE_PATTERN = re.compile(
    r"\b(none|no drainage|dry|scant|minimal|light|small|moderate|mod|large|heavy|copious)\b",
    re.IGNORECASE
)

DRAINAGE_MAP = {
    "none": "none", "no drainage": "none", "dry": "none",
    "scant": "light", "minimal": "light", "light": "light", "small": "light",
    "moderate": "moderate", "mod": "moderate",
    "large": "heavy", "heavy": "heavy", "copious": "heavy",
}

# Wound type keywords (order matters — check more specific first)
WOUND_TYPE_PATTERNS = [
    (re.compile(r"diabetic\s+foot\s+ulcer|DFU", re.IGNORECASE), "diabetic_foot_ulcer"),
    (re.compile(r"\bdiabetic\b", re.IGNORECASE), "diabetic"),
    (re.compile(r"venous\s+stasis|venous\s+ulcer|\bvenous\b", re.IGNORECASE), "venous"),
    (re.compile(r"arterial\s+ulcer|\barterial\b", re.IGNORECASE), "arterial"),
    (re.compile(r"pressure\s+(ulcer|injury|sore|wound)", re.IGNORECASE), "pressure_ulcer"),
    (re.compile(r"surgical\s+site|SSI|post.?op\s+wound|\bsurgical\b", re.IGNORECASE), "surgical"),
    (re.compile(r"\babscess\b", re.IGNORECASE), "abscess"),
    (re.compile(r"\bburn\b", re.IGNORECASE), "burn"),
    (re.compile(r"\bulcer\b", re.IGNORECASE), "ulcer_unspecified"),
]

# Stage for pressure ulcers
STAGE_PATTERN = re.compile(
    r"stage\s*(I{1,4}V?|\d+)|unstageable|un-stageable",
    re.IGNORECASE
)

ROMAN_TO_INT = {"I": 1, "II": 2, "III": 3, "IV": 4}

# Location keywords (anatomy)
LOCATION_PATTERN = re.compile(
    r"(?:location|site|wound\s+site)[:\s]+([^\n,;\.]{3,40})|"
    r"\b(sacrum|sacral|heel|coccyx|trochanter|ischium|malleolus|ankle|foot|toe|"
    r"shin|calf|knee|elbow|hip|buttock|shoulder|back|abdomen|gluteal|"
    r"cervical|plantar|malleolus|trochanter|ischial|sacral\s+region)\b",
    re.IGNORECASE
)
# "Abscess Right cervical measures" / "Diabetic Left plantar measures"
LOCATION_INLINE = re.compile(
    r"(?:abscess|pressure\s+ulcer|diabetic|venous|burn|surgical|arterial)\s+"
    r"((?:right|left|bilateral)\s+(?:[\w]+\s*){1,4}?)\s+measures",
    re.IGNORECASE
)
# "at Right cervical wound site"
LOCATION_AT_SITE = re.compile(
    r"at\s+((?:right|left|bilateral)\s+[\w\s]+?)\s+wound\s+site",
    re.IGNORECASE
)
# Envive: "Pressure Ulcer to Right hip / Measures"
LOCATION_TO = re.compile(
    r"(?:ulcer|abscess|infection|burn|diabetic|venous)\s+to\s+"
    r"((?:right|left|bilateral)\s+[\w\s/]+?)(?:\s*/|\s+measures|\s+/)",
    re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_stage(text: str):
    """Return numeric stage or 'unstageable' or None."""
    if not text:
        return None
    m = STAGE_PATTERN.search(text)
    if not m:
        return None
    raw = m.group(1) or m.group(0)
    raw = raw.strip()
    if re.match(r"unstageable|un-stageable", raw, re.IGNORECASE):
        return "unstageable"
    if raw.isdigit():
        return int(raw)
    return ROMAN_TO_INT.get(raw.upper())


def parse_drainage(text: str):
    m = DRAINAGE_PATTERN.search(text)
    if not m:
        return None
    return DRAINAGE_MAP.get(m.group(0).lower())


def parse_wound_type(text: str):
    for pattern, wtype in WOUND_TYPE_PATTERNS:
        if pattern.search(text):
            return wtype
    return None


def parse_measurements(text: str):
    """
    Return (length, width, depth) or (None, None, None).
    Tries patterns from most-specific to least-specific.
    """
    # 1. Full 3D with cm after each: "4.3 cm x 1.8 cm x 0.3 cm"
    m = MEAS_3D_EACH.search(text)
    if m:
        return float(m.group(1)), float(m.group(2)), float(m.group(3))

    # 2. Full 3D with cm at end: "3.2 x 2.1 x 0.4 cm"
    m = MEAS_3D_END.search(text)
    if m:
        return float(m.group(1)), float(m.group(2)), float(m.group(3))

    # 3. 2D with cm after each: "2.9 cm x 2.8 cm" (Envive — depth separate or absent)
    m2 = MEAS_2D_EACH.search(text)
    if m2:
        length, width = float(m2.group(1)), float(m2.group(2))
        # Try to find depth separately in the same text
        dp = DEP_PROSE.search(text)
        if not dp:
            dp = DEP_PATTERN.search(text)
        depth = float(dp.group(1) or dp.group(2)) if dp else None
        return length, width, depth

    # 4. 2D with cm at end: "5.9 x 4.5cm" (prose — look for depth separately)
    m2 = MEAS_2D_END.search(text)
    if m2:
        length, width = float(m2.group(1)), float(m2.group(2))
        dp = DEP_PROSE.search(text)
        if not dp:
            dp = DEP_PATTERN.search(text)
        depth = float(dp.group(1) or dp.group(2)) if dp else None
        return length, width, depth

    # 5. Labeled individual fields: "Length: 3.2 cm"
    lm = LEN_PATTERN.search(text)
    wm = WID_PATTERN.search(text)
    dm = DEP_PATTERN.search(text) or DEP_PROSE.search(text)
    if lm or wm or dm:
        return (
            float(lm.group(1)) if lm else None,
            float(wm.group(1)) if wm else None,
            float((dm.group(1) or dm.group(2))) if dm else None,
        )

    return None, None, None


def parse_location(text: str):
    for pattern in (LOCATION_AT_SITE, LOCATION_INLINE, LOCATION_TO, LOCATION_PATTERN):
        m = pattern.search(text)
        if not m:
            continue
        loc = (m.group(1) or m.group(2) or "").strip()
        if loc and len(loc) >= 3:
            return loc.title()
    return None


# ---------------------------------------------------------------------------
# Extract from assessment raw_json
# ---------------------------------------------------------------------------

# Map question text -> result field and optional transform
_QUESTION_MAP = {
    "length (cm)":      ("length_cm",        float),
    "width (cm)":       ("width_cm",         float),
    "depth (cm)":       ("depth_cm",         float),
    "wound type":       ("wound_type",        lambda v: v.lower().replace(" ", "_")),
    "type":             ("wound_type",        lambda v: v.lower().replace(" ", "_")),
    "stage":            ("stage",             lambda v: v),
    "location":         ("location",          lambda v: v.strip().title()),
    "drainage amount":  ("drainage_amount",   lambda v: v.lower()),
}

def _parse_question_answer(question: str, answer: str, result: dict):
    """Map one Q&A pair to a result field."""
    q = question.lower().strip()
    for key, (field, transform) in _QUESTION_MAP.items():
        if key in q and answer and answer.strip() not in ("", "N/A", "n/a"):
            if field not in result:  # don't overwrite already-set fields
                try:
                    result[field] = transform(answer.strip())
                except (ValueError, TypeError):
                    pass
            return


def extract_from_assessment(raw_json_str: str) -> dict:
    """
    Parse the nested sections JSON format used by the PCC assessments.

    Two sub-formats exist in the data:
      A) Structured — sections with individual labeled questions:
            {"question": "Length (cm)", "answer": "3.2"}
      B) Narrative — single question whose answer is a text string:
            {"question": "Wound narrative",
             "answer": "Pressure Ulcer to Sacrum / Measures 2.9 cm x 2.8 cm / ..."}
    """
    if not raw_json_str:
        return {}
    try:
        data = json.loads(raw_json_str)
    except json.JSONDecodeError:
        return {}

    result = {}
    sections = data.get("sections", [])

    for section in sections:
        for qa in section.get("questions", []):
            question = qa.get("question", "")
            answer   = qa.get("answer", "")

            if "narrative" in question.lower() or "wound status" in question.lower():
                # Format B — run regex extraction on the narrative text
                narrative_result = extract_from_note(answer)
                for k, v in narrative_result.items():
                    if k not in result and v is not None:
                        result[k] = v
            else:
                # Format A — structured Q&A
                _parse_question_answer(question, answer, result)

    return result


# ---------------------------------------------------------------------------
# Extract from note text
# ---------------------------------------------------------------------------

def extract_from_note(note_text: str) -> dict:
    if not note_text:
        return {}
    result = {}

    wtype = parse_wound_type(note_text)
    if wtype:
        result["wound_type"] = wtype

    stage = parse_stage(note_text)
    if stage is not None:
        result["stage"] = stage

    loc = parse_location(note_text)
    if loc:
        result["location"] = loc

    length, width, depth = parse_measurements(note_text)
    if length is not None:
        result["length_cm"] = length
    if width is not None:
        result["width_cm"] = width
    if depth is not None:
        result["depth_cm"] = depth

    drainage = parse_drainage(note_text)
    if drainage:
        result["drainage_amount"] = drainage

    return result


# ---------------------------------------------------------------------------
# Merge extraction results — assessments take priority field-by-field
# ---------------------------------------------------------------------------

def merge_extractions(from_assessments: list[dict], from_notes: list[dict]) -> dict:
    """
    Combine all assessment extractions first, then fill gaps from notes.
    """
    merged = {}

    for ext in from_assessments:
        for k, v in ext.items():
            if v is not None and k not in merged:
                merged[k] = v

    for ext in from_notes:
        for k, v in ext.items():
            if v is not None and k not in merged:
                merged[k] = v

    return merged


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_for_patient(conn: sqlite3.Connection, internal_id: int) -> dict:
    """
    Given internal patient id, pull assessments + notes and extract wound fields.
    Returns a dict with wound_type, stage, location, length_cm, width_cm, depth_cm,
    drainage_amount, and source ('assessment', 'note', 'both', 'none').
    """
    cur = conn.cursor()

    cur.execute(
        "SELECT raw_json FROM assessments WHERE patient_id=? AND is_current=1",
        (internal_id,)
    )
    assessment_rows = cur.fetchall()

    cur.execute(
        "SELECT note_text FROM notes WHERE patient_id=? AND is_current=1",
        (internal_id,)
    )
    note_rows = cur.fetchall()

    assessment_extractions = [
        extract_from_assessment(row[0]) for row in assessment_rows if row[0]
    ]
    note_extractions = [
        extract_from_note(row[0]) for row in note_rows if row[0]
    ]

    assessment_has_data = any(bool(e) for e in assessment_extractions)
    note_has_data = any(bool(e) for e in note_extractions)

    assessment_only = merge_extractions(assessment_extractions, [])
    note_only = merge_extractions([], note_extractions)
    merged = merge_extractions(assessment_extractions, note_extractions)

    if assessment_has_data and note_has_data:
        source = "both"
    elif assessment_has_data:
        source = "assessment"
    elif note_has_data:
        source = "note"
    else:
        source = "none"

    merged["extraction_source"] = source
    merged["_assessment_fields"] = assessment_only
    merged["_note_fields"] = note_only
    return merged


def run_extraction(db_path: str = DB_PATH) -> dict:
    """
    Run extraction for all patients. Returns dict of internal_id -> wound fields.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, patient_id FROM patients")
    patients = cur.fetchall()

    results = {}
    for internal_id, patient_id in patients:
        results[patient_id] = extract_for_patient(conn, internal_id)

    conn.close()
    log.info("Extraction complete for %d patients", len(results))
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = run_extraction()
    found = sum(1 for v in results.values() if v.get("wound_type"))
    print(f"Wound type extracted for {found}/{len(results)} patients")
