"""
Gemini LLM fallback extraction for patients where regex left gaps.
Set GEMINI_API_KEY (or GOOGLE_API_KEY) in environment.

Run via: python pipeline.py --skip-ingest --use-llm

Strategy: 2 API calls, 14 Medicare-B patients per call, with Gemini rate-limit retries.
"""

import json
import logging
import os
import re
import sqlite3
import time

import requests

log = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)
BATCH_SIZE = 14
MAX_RETRIES = 8
MAX_OUTPUT_TOKENS = 4096
MIN_INTER_BATCH_SECONDS = 4.0  # free tier ~15 RPM

SYSTEM_PROMPT = """You extract wound care billing fields from clinical text.
Return ONLY valid JSON — no markdown, no explanation.

For multi-wound notes, use the PRIMARY wound (first wound described).
Drainage must be one of: none, light, moderate, heavy.
Stage is only for pressure ulcers (integer 2-4 or "unstageable"); null otherwise.
For pressure ulcers, stage may appear in ICD-10 descriptions (e.g. L89.152 = stage 2).

JSON schema per patient:
{
  "patient_id": "FA-001",
  "wound_type": "pressure_ulcer",
  "stage": 2,
  "location": "Sacrum",
  "length_cm": 3.2,
  "width_cm": 2.1,
  "depth_cm": 0.4,
  "drainage_amount": "moderate"
}

Return a JSON array with one object per patient, in the same order listed.
Use null for fields truly not documented. Do not guess measurements."""


def _api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY not set — skip LLM or export your Gemini API key"
        )
    return key


def _parse_retry_seconds(resp: requests.Response, attempt: int) -> float:
    try:
        err = resp.json().get("error", {})
        msg = err.get("message", "")
        m = re.search(r"retry in ([\d.]+)s", msg, re.IGNORECASE)
        if m:
            return max(float(m.group(1)), MIN_INTER_BATCH_SECONDS)
    except (ValueError, AttributeError):
        pass
    return MIN_INTER_BATCH_SECONDS * (attempt + 1)


def _gemini_chat(user_prompt: str) -> str:
    """POST to Gemini generateContent with retry on 429."""
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": MAX_OUTPUT_TOKENS,
            "responseMimeType": "application/json",
        },
    }

    for attempt in range(MAX_RETRIES):
        resp = requests.post(
            GEMINI_API_URL,
            params={"key": _api_key()},
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=120,
        )
        if resp.status_code == 429:
            wait = _parse_retry_seconds(resp, attempt)
            log.warning(
                "Gemini 429 — waiting %.1fs (attempt %d/%d)",
                wait, attempt + 1, MAX_RETRIES,
            )
            time.sleep(wait)
            continue
        resp.raise_for_status()
        data = resp.json()
        parts = data["candidates"][0]["content"]["parts"]
        return parts[0]["text"]

    raise RuntimeError(f"Gemini rate limit: failed after {MAX_RETRIES} retries")


def _parse_json_response(text: str) -> list[dict]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    if isinstance(data, dict):
        if "patients" in data:
            return data["patients"]
        return [data]
    return data


_WOUND_SECTIONS = frozenset({"LOCATION", "WOUND", "DRAINAGE", "WOUND_BED"})
_NOTE_MAX_CHARS = 500


def _compact_assessment(raw_json_str: str) -> str:
    """Flatten assessment JSON to wound-relevant Q&A."""
    if not raw_json_str:
        return ""
    try:
        data = json.loads(raw_json_str)
    except json.JSONDecodeError:
        return raw_json_str[:_NOTE_MAX_CHARS]
    lines: list[str] = []
    for sec in data.get("sections", []):
        name = (sec.get("sectionName") or "").upper()
        if name not in _WOUND_SECTIONS:
            continue
        lines.append(f"[{name}]")
        for q in sec.get("questions", []):
            question = (q.get("question") or "").strip()
            answer = (q.get("answer") or "").strip()
            if question:
                lines.append(f"  {question}: {answer}")
    return "\n".join(lines) if lines else raw_json_str[:_NOTE_MAX_CHARS]


def _compact_note(text: str) -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) <= _NOTE_MAX_CHARS:
        return text
    return text[:_NOTE_MAX_CHARS] + "…"


def _gather_clinical_bundle(
    conn: sqlite3.Connection,
    patient_id: str,
    internal_id: int,
    missing_fields: list[str] | None = None,
) -> str:
    cur = conn.cursor()
    parts = [f"Patient: {patient_id}"]
    if missing_fields:
        parts.append(f"NEED: {', '.join(missing_fields)}")

    cur.execute(
        "SELECT icd10_code, icd10_description, clinical_status FROM diagnoses WHERE patient_id=?",
        (patient_id,),
    )
    dx = cur.fetchall()
    if dx:
        parts.append("DIAGNOSES:")
        for code, desc, status in dx:
            parts.append(f"  {code} ({status}): {desc}")

    cur.execute(
        "SELECT assessment_type, assessment_date, raw_json FROM assessments "
        "WHERE patient_id=? AND is_current=1",
        (internal_id,),
    )
    for atype, adate, raw in cur.fetchall():
        parts.append(f"ASSESSMENT ({atype}, {adate}):")
        parts.append(_compact_assessment(raw or ""))

    cur.execute(
        "SELECT note_type, effective_date, note_text FROM notes "
        "WHERE patient_id=? AND is_current=1 ORDER BY effective_date",
        (internal_id,),
    )
    for ntype, edate, text in cur.fetchall():
        parts.append(f"NOTE ({ntype}, {edate}):")
        parts.append(_compact_note(text or ""))

    return "\n".join(parts)


def _merge_llm_into_extraction(existing: dict, llm_fields: dict) -> dict:
    """Fill only empty fields — never overwrite regex/assessment values."""
    merged = dict(existing)
    for key in ("wound_type", "stage", "location", "length_cm", "width_cm", "depth_cm", "drainage_amount"):
        if merged.get(key) not in (None, "", 0):
            continue
        val = llm_fields.get(key)
        if val is None or val == "":
            continue
        if key in ("length_cm", "width_cm", "depth_cm"):
            try:
                merged[key] = float(val)
            except (ValueError, TypeError):
                continue
        elif key == "stage":
            if str(val).lower() in ("unstageable", "un-stageable"):
                merged[key] = "unstageable"
            else:
                try:
                    merged[key] = int(val)
                except (ValueError, TypeError):
                    merged[key] = val
        elif key == "drainage_amount":
            merged[key] = str(val).lower()
        else:
            merged[key] = str(val).lower().replace(" ", "_") if key == "wound_type" else str(val)
    if llm_fields:
        src = merged.get("extraction_source") or "none"
        merged["extraction_source"] = src if "+llm" in src else src + "+llm"
    return merged


def _mcb_patient_ids(conn: sqlite3.Connection) -> set[str]:
    """Return patient_ids with active Medicare Part B coverage."""
    from eligibility import has_active_medicare_b

    cur = conn.cursor()
    cur.execute("SELECT patient_id FROM patients")
    mcb = set()
    for (pid,) in cur.fetchall():
        cur.execute(
            "SELECT payer_code, effective_to FROM coverage WHERE patient_id=?",
            (pid,),
        )
        rows = [dict(zip(["payer_code", "effective_to"], r)) for r in cur.fetchall()]
        if has_active_medicare_b(rows)[0]:
            mcb.add(pid)
    return mcb


def fill_gaps_with_llm(
    db_path: str,
    extractions: dict,
    patient_ids: list[str] | None = None,
) -> dict:
    """
    Run Gemini on Medicare-B patients still missing required fields.
    Uses ceil(n/14) API calls — typically 2 calls for ~26 flagged patients.
    """
    from eligibility import get_missing_fields

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, patient_id FROM patients")
    id_map = {pid: iid for iid, pid in cur.fetchall()}
    mcb_ids = _mcb_patient_ids(conn)

    if patient_ids is None:
        patient_ids = sorted(
            pid for pid, data in extractions.items()
            if pid in mcb_ids and get_missing_fields(data)
        )

    if not patient_ids:
        log.info("LLM: no Medicare-B patients need gap-filling")
        conn.close()
        return extractions

    num_batches = (len(patient_ids) + BATCH_SIZE - 1) // BATCH_SIZE
    log.info(
        "LLM (%s): %d Medicare-B patients, %d API call(s), %d per call",
        GEMINI_MODEL, len(patient_ids), num_batches, BATCH_SIZE,
    )

    updated = dict(extractions)

    for batch_num, i in enumerate(range(0, len(patient_ids), BATCH_SIZE), start=1):
        if batch_num > 1:
            log.info("Waiting %.1fs before next Gemini batch (rate limit)", MIN_INTER_BATCH_SECONDS)
            time.sleep(MIN_INTER_BATCH_SECONDS)

        batch = patient_ids[i : i + BATCH_SIZE]
        bundles = [
            _gather_clinical_bundle(
                conn, pid, id_map[pid], get_missing_fields(updated.get(pid, {}))
            )
            for pid in batch
        ]

        user_prompt = (
            f"Extract wound fields for {len(batch)} patients below. "
            f"Return a JSON array with exactly {len(batch)} objects, one per patient.\n\n"
            + "\n\n---\n\n".join(bundles)
        )

        try:
            log.info("LLM call %d/%d — patients: %s ... %s", batch_num, num_batches, batch[0], batch[-1])
            raw = _gemini_chat(user_prompt)
            results = _parse_json_response(raw)
            log.info("LLM call %d: got %d result(s)", batch_num, len(results))

            by_pid = {r.get("patient_id"): r for r in results if r.get("patient_id")}
            for idx, pid in enumerate(batch):
                llm_row = by_pid.get(pid)
                if not llm_row and idx < len(results) and not results[idx].get("patient_id"):
                    llm_row = {**results[idx], "patient_id": pid}
                if llm_row:
                    updated[pid] = _merge_llm_into_extraction(updated.get(pid, {}), llm_row)
                else:
                    log.warning("LLM: no result for %s", pid)
        except Exception as e:
            log.error("LLM call %d failed: %s", batch_num, e)

    conn.close()
    still_missing = sum(1 for pid in patient_ids if get_missing_fields(updated.get(pid, {})))
    log.info("LLM complete. Still missing fields: %d / %d", still_missing, len(patient_ids))
    return updated
