"""
Method 2: ThreadPoolExecutor with 10 workers — current production approach.
"""

import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from common import get_test_patients, fetch_one_patient_sync


def run(patients: list, workers: int = 10) -> float:
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(fetch_one_patient_sync, p) for p in patients]
        for f in as_completed(futures):
            f.result()
    elapsed = time.perf_counter() - start
    return elapsed


if __name__ == "__main__":
    patients = get_test_patients()
    print(f"Running ThreadPool(10) on {len(patients)} patients...")
    elapsed = run(patients, workers=10)
    print(f"Threads(10): {elapsed:.2f}s for {len(patients)} patients "
          f"({elapsed/len(patients):.2f}s/patient)")
    print(f"Projected for 300 patients: {elapsed/len(patients)*300/60:.1f} minutes")
