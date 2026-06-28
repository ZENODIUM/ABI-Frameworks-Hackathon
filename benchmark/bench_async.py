"""
Method 4: asyncio + aiohttp — true async I/O, no threads.
All 4 per-patient requests fire concurrently per patient, all patients run concurrently.
"""

import asyncio
import time
import aiohttp

BASE_URL = "https://hackathon.prod.pulsefoundry.ai"
MAX_RETRIES = 8
CONCURRENCY = 30  # max simultaneous open connections


async def retry_get_async(session: aiohttp.ClientSession, url: str, params: dict):
    for attempt in range(MAX_RETRIES):
        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 429:
                    wait = int(resp.headers.get("Retry-After", 3))
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                return await resp.json()
        except Exception:
            await asyncio.sleep(2)
    return []


async def fetch_one_patient_async(session: aiohttp.ClientSession, semaphore: asyncio.Semaphore, patient: dict):
    """Fetch all 4 endpoints for one patient concurrently (within semaphore)."""
    pid_str = patient["patient_id"]
    pid_int = patient["id"]
    async with semaphore:
        await asyncio.gather(
            retry_get_async(session, f"{BASE_URL}/pcc/diagnoses",  {"patient_id": pid_str}),
            retry_get_async(session, f"{BASE_URL}/pcc/coverage",   {"patient_id": pid_str}),
            retry_get_async(session, f"{BASE_URL}/pcc/notes",      {"patient_id": pid_int}),
            retry_get_async(session, f"{BASE_URL}/pcc/assessments",{"patient_id": pid_int}),
        )


async def run_async(patients: list) -> float:
    semaphore = asyncio.Semaphore(CONCURRENCY)
    connector = aiohttp.TCPConnector(limit=CONCURRENCY)
    start = time.perf_counter()
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [fetch_one_patient_async(session, semaphore, p) for p in patients]
        await asyncio.gather(*tasks)
    elapsed = time.perf_counter() - start
    return elapsed


def run(patients: list) -> float:
    return asyncio.run(run_async(patients))


if __name__ == "__main__":
    import requests as req
    import sys
    sys.path.insert(0, ".")
    from common import get_test_patients
    patients = get_test_patients()
    print(f"Running async/aiohttp on {len(patients)} patients...")
    elapsed = run(patients)
    print(f"Async: {elapsed:.2f}s for {len(patients)} patients "
          f"({elapsed/len(patients):.2f}s/patient)")
    print(f"Projected for 300 patients: {elapsed/len(patients)*300/60:.1f} minutes")
