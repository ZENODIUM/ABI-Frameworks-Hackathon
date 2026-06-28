"""
Shared utilities for all benchmark methods.
Uses 30 patients (FA-001 to FA-030) as the test subset — same patients for every method.
"""

import time
import requests

BASE_URL = "https://hackathon.prod.pulsefoundry.ai"
MAX_RETRIES = 8
TEST_FACILITY = 101
TEST_PATIENT_LIMIT = 30  # subset for fair comparison across methods


def get_test_patients() -> list:
    """Fetch first N patients from facility 101 for benchmarking."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(f"{BASE_URL}/pcc/patients", params={"facility_id": TEST_FACILITY}, timeout=15)
            if resp.status_code == 429:
                time.sleep(int(resp.headers.get("Retry-After", 3)))
                continue
            resp.raise_for_status()
            patients = resp.json()
            return patients[:TEST_PATIENT_LIMIT]
        except Exception as e:
            time.sleep(2)
    raise RuntimeError("Could not fetch patients")


def retry_get_sync(url: str, params: dict) -> list | dict:
    """Synchronous GET with retry on 429."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 3))
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception:
            time.sleep(2)
    return []


def fetch_one_patient_sync(patient: dict):
    """Fetch all 4 endpoints for one patient synchronously. Returns fetched data."""
    pid_str = patient["patient_id"]
    pid_int = patient["id"]
    retry_get_sync(f"{BASE_URL}/pcc/diagnoses", {"patient_id": pid_str})
    retry_get_sync(f"{BASE_URL}/pcc/coverage",  {"patient_id": pid_str})
    retry_get_sync(f"{BASE_URL}/pcc/notes",      {"patient_id": pid_int})
    retry_get_sync(f"{BASE_URL}/pcc/assessments",{"patient_id": pid_int})
