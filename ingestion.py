"""
Fetch all patient data from the mock PCC API and store in SQLite.

Two modes:
  Full ingest   : fetches all patients from all facilities (first run)
  Incremental   : fetches only patients modified since last successful sync

Uses async/aiohttp for maximum throughput (~34x faster than sequential).
Handles 30% rate-limit (429) with retry using the server's Retry-After header.
"""

import asyncio
import sqlite3
import time
import logging
import json
from datetime import datetime, timezone
import aiohttp

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

BASE_URL = "https://hackathon.prod.pulsefoundry.ai"
FACILITY_IDS = [101, 102, 103]
DB_PATH = "abi.db"
MAX_RETRIES = 8
CONCURRENCY = 30  # max simultaneous open connections


# ---------------------------------------------------------------------------
# DB setup
# ---------------------------------------------------------------------------

def init_db(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY,
            facility_id INTEGER,
            patient_id TEXT UNIQUE,
            first_name TEXT,
            last_name TEXT,
            birth_date TEXT,
            gender TEXT,
            primary_payer_code TEXT,
            last_modified_at TEXT,
            is_new_admission INTEGER
        );

        CREATE TABLE IF NOT EXISTS diagnoses (
            id INTEGER PRIMARY KEY,
            patient_id TEXT,
            icd10_code TEXT,
            icd10_description TEXT,
            clinical_status TEXT,
            onset_date TEXT,
            last_modified_at TEXT
        );

        CREATE TABLE IF NOT EXISTS coverage (
            id INTEGER PRIMARY KEY,
            patient_id TEXT,
            payer_name TEXT,
            payer_code TEXT,
            payer_type TEXT,
            effective_from TEXT,
            effective_to TEXT,
            last_modified_at TEXT
        );

        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY,
            patient_id INTEGER,
            note_type TEXT,
            effective_date TEXT,
            note_text TEXT,
            created_by TEXT,
            is_current INTEGER
        );

        CREATE TABLE IF NOT EXISTS assessments (
            id INTEGER PRIMARY KEY,
            patient_id INTEGER,
            assessment_type TEXT,
            status TEXT,
            assessment_date TEXT,
            raw_json TEXT,
            is_current INTEGER
        );

        CREATE TABLE IF NOT EXISTS sync_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            last_sync_at TEXT,
            last_sync_mode TEXT,
            patients_synced INTEGER
        );
    """)
    conn.commit()


def get_last_sync(conn: sqlite3.Connection) -> str | None:
    cur = conn.cursor()
    cur.execute("SELECT last_sync_at FROM sync_state WHERE id=1")
    row = cur.fetchone()
    return row[0] if row else None


def save_sync_state(conn: sqlite3.Connection, mode: str, patients_synced: int):
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO sync_state (id, last_sync_at, last_sync_mode, patients_synced)
        VALUES (1, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            last_sync_at=excluded.last_sync_at,
            last_sync_mode=excluded.last_sync_mode,
            patients_synced=excluded.patients_synced
    """, (now, mode, patients_synced))
    conn.commit()
    return now


# ---------------------------------------------------------------------------
# Upsert helpers (synchronous, called under a lock)
# ---------------------------------------------------------------------------

def _upsert_patients(conn, patients):
    cur = conn.cursor()
    for p in patients:
        cur.execute("""
            INSERT OR REPLACE INTO patients
            (id, facility_id, patient_id, first_name, last_name, birth_date,
             gender, primary_payer_code, last_modified_at, is_new_admission)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            p.get("id"), p.get("facility_id"), p.get("patient_id"),
            p.get("first_name"), p.get("last_name"), p.get("birth_date"),
            p.get("gender"), p.get("primary_payer_code"),
            p.get("last_modified_at"), int(p.get("is_new_admission") or 0)
        ))
    conn.commit()


def _upsert_diagnoses(conn, rows):
    cur = conn.cursor()
    for d in rows:
        cur.execute("""
            INSERT OR REPLACE INTO diagnoses
            (id, patient_id, icd10_code, icd10_description, clinical_status, onset_date, last_modified_at)
            VALUES (?,?,?,?,?,?,?)
        """, (
            d.get("id"), d.get("patient_id"), d.get("icd10_code"),
            d.get("icd10_description"), d.get("clinical_status"),
            d.get("onset_date"), d.get("last_modified_at")
        ))
    conn.commit()


def _upsert_coverage(conn, rows):
    cur = conn.cursor()
    for c in rows:
        cur.execute("""
            INSERT OR REPLACE INTO coverage
            (id, patient_id, payer_name, payer_code, payer_type, effective_from, effective_to, last_modified_at)
            VALUES (?,?,?,?,?,?,?,?)
        """, (
            c.get("id"), c.get("patient_id"), c.get("payer_name"),
            c.get("payer_code"), c.get("payer_type"),
            c.get("effective_from"), c.get("effective_to"), c.get("last_modified_at")
        ))
    conn.commit()


def _upsert_notes(conn, rows):
    cur = conn.cursor()
    for n in rows:
        cur.execute("""
            INSERT OR REPLACE INTO notes
            (id, patient_id, note_type, effective_date, note_text, created_by, is_current)
            VALUES (?,?,?,?,?,?,?)
        """, (
            n.get("id"), n.get("patient_id"), n.get("note_type"),
            n.get("effective_date"), n.get("note_text"),
            n.get("created_by"), int(n.get("is_current") or 0)
        ))
    conn.commit()


def _upsert_assessments(conn, rows):
    cur = conn.cursor()
    for a in rows:
        cur.execute("""
            INSERT OR REPLACE INTO assessments
            (id, patient_id, assessment_type, status, assessment_date, raw_json, is_current)
            VALUES (?,?,?,?,?,?,?)
        """, (
            a.get("id"), a.get("patient_id"), a.get("assessment_type"),
            a.get("status"), a.get("assessment_date"),
            a.get("raw_json"), int(a.get("is_current") or 0)
        ))
    conn.commit()


# ---------------------------------------------------------------------------
# Async fetch helpers
# ---------------------------------------------------------------------------

async def retry_get(session: aiohttp.ClientSession, url: str, params: dict) -> list | dict:
    """Async GET with retry on 429 using server's Retry-After."""
    for attempt in range(MAX_RETRIES):
        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 429:
                    wait = int(resp.headers.get("Retry-After", 3))
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                return await resp.json()
        except asyncio.TimeoutError:
            await asyncio.sleep(2)
        except Exception as e:
            await asyncio.sleep(2)
    log.error("Failed after %d retries: %s %s", MAX_RETRIES, url, params)
    return []


async def fetch_patients_for_facility(
    session: aiohttp.ClientSession,
    facility_id: int,
    since: str | None = None,
) -> list:
    params = {"facility_id": facility_id}
    if since:
        params["since"] = since
    result = await retry_get(session, f"{BASE_URL}/pcc/patients", params)
    return result if isinstance(result, list) else []


async def fetch_patient_clinical_data(
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    db_lock: asyncio.Lock,
    db_path: str,
    patient: dict,
    since: str | None = None,
):
    """Fetch all 4 endpoints for one patient concurrently, then write to DB."""
    pid_str = patient["patient_id"]
    pid_int = patient["id"]

    # Build params — notes and assessments support `since`, diagnoses/coverage don't
    note_params = {"patient_id": pid_int}
    assess_params = {"patient_id": pid_int}
    if since:
        note_params["since"] = since
        assess_params["since"] = since

    async with semaphore:
        diagnoses, coverage, notes, assessments = await asyncio.gather(
            retry_get(session, f"{BASE_URL}/pcc/diagnoses",   {"patient_id": pid_str}),
            retry_get(session, f"{BASE_URL}/pcc/coverage",    {"patient_id": pid_str}),
            retry_get(session, f"{BASE_URL}/pcc/notes",       note_params),
            retry_get(session, f"{BASE_URL}/pcc/assessments", assess_params),
        )

    async with db_lock:
        conn = sqlite3.connect(db_path)
        _upsert_diagnoses(conn, diagnoses if isinstance(diagnoses, list) else [])
        _upsert_coverage(conn,  coverage  if isinstance(coverage,  list) else [])
        _upsert_notes(conn,     notes     if isinstance(notes,     list) else [])
        _upsert_assessments(conn, assessments if isinstance(assessments, list) else [])
        conn.close()


# ---------------------------------------------------------------------------
# Main async ingest
# ---------------------------------------------------------------------------

async def _ingest_async(db_path: str, since: str | None = None):
    semaphore = asyncio.Semaphore(CONCURRENCY)
    db_lock = asyncio.Lock()
    connector = aiohttp.TCPConnector(limit=CONCURRENCY)

    async with aiohttp.ClientSession(connector=connector) as session:

        # Fetch patients from all 3 facilities (with optional since filter)
        facility_results = await asyncio.gather(*[
            fetch_patients_for_facility(session, fid, since)
            for fid in FACILITY_IDS
        ])

        all_patients = []
        conn = sqlite3.connect(db_path)
        for fid, patients in zip(FACILITY_IDS, facility_results):
            _upsert_patients(conn, patients)
            all_patients.extend(patients)
            log.info("  Facility %d: %d patients %s",
                     fid, len(patients),
                     "(modified since last sync)" if since else "")
        conn.close()

        if not all_patients:
            log.info("No patients to update.")
            return 0

        log.info("Fetching clinical data for %d patients...", len(all_patients))
        start = time.perf_counter()

        tasks = [
            fetch_patient_clinical_data(session, semaphore, db_lock, db_path, p, since)
            for p in all_patients
        ]
        await asyncio.gather(*tasks)

        elapsed = time.perf_counter() - start
        log.info("Clinical data fetched in %.1fs (%.2fs/patient)", elapsed, elapsed / len(all_patients))

    return len(all_patients)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ingest_all(db_path: str = DB_PATH, incremental: bool = False) -> tuple[int, str]:
    """
    Full or incremental ingest.

    Full       : fetches all 300 patients from scratch (first run or forced refresh)
    Incremental: only fetches patients modified since the last successful sync

    Returns (patients_synced, mode)
    """
    conn = sqlite3.connect(db_path)
    init_db(conn)

    last_sync = get_last_sync(conn) if incremental else None
    conn.close()

    mode = "incremental" if (incremental and last_sync) else "full"

    if mode == "incremental":
        log.info("INCREMENTAL SYNC — fetching records modified since %s", last_sync)
    else:
        log.info("FULL INGEST — fetching all patients from all facilities")

    patients_synced = asyncio.run(_ingest_async(db_path, since=last_sync if mode == "incremental" else None))

    # Save successful sync timestamp
    conn = sqlite3.connect(db_path)
    sync_time = save_sync_state(conn, mode, patients_synced)
    conn.close()

    log.info("Sync complete. Mode=%s, patients=%d, timestamp=%s", mode, patients_synced, sync_time)
    return patients_synced, mode


if __name__ == "__main__":
    import sys
    incremental = "--incremental" in sys.argv
    count, mode = ingest_all(incremental=incremental)
    print(f"Done. Mode={mode}, patients synced={count}")
