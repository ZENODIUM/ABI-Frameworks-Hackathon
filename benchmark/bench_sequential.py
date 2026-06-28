"""
Method 1: Sequential — one patient at a time, no parallelism.
Baseline to compare everything else against.
"""

import time
from common import get_test_patients, fetch_one_patient_sync, TEST_PATIENT_LIMIT


def run(patients: list) -> float:
    start = time.perf_counter()
    for patient in patients:
        fetch_one_patient_sync(patient)
    elapsed = time.perf_counter() - start
    return elapsed


if __name__ == "__main__":
    patients = get_test_patients()
    print(f"Running sequential on {len(patients)} patients...")
    elapsed = run(patients)
    print(f"Sequential: {elapsed:.2f}s for {len(patients)} patients "
          f"({elapsed/len(patients):.2f}s/patient)")
    print(f"Projected for 300 patients: {elapsed/len(patients)*300/60:.1f} minutes")
