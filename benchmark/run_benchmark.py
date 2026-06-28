"""
Run all 4 ingestion methods on the same 30-patient subset and print a comparison table.
Each method runs once. Results are projected to full 300 patients.
"""

import sys
import time

sys.path.insert(0, ".")

from common import get_test_patients

print("=" * 60)
print("ABI INGESTION BENCHMARK")
print("=" * 60)
print(f"Fetching test patients...")

patients = get_test_patients()
n = len(patients)
print(f"Test set: {n} patients (FA-001 to FA-0{n:02d})")
print(f"Each patient = 4 API calls (diagnoses, coverage, notes, assessments)")
print(f"API has ~30% rate-limit (429) chance per request")
print()

results = {}

# --- Method 1: Sequential ---
print(f"[1/4] Running SEQUENTIAL...")
from bench_sequential import run as run_seq
t = run_seq(patients)
results["Sequential"] = t
print(f"      Done: {t:.2f}s\n")

# --- Method 2: Threads 10 ---
print(f"[2/4] Running THREAD POOL (10 workers)...")
from bench_threads_10 import run as run_t10
t = run_t10(patients, workers=10)
results["Threads (10)"] = t
print(f"      Done: {t:.2f}s\n")

# --- Method 3: Threads 25 ---
print(f"[3/4] Running THREAD POOL (25 workers)...")
from bench_threads_25 import run as run_t25
t = run_t25(patients, workers=25)
results["Threads (25)"] = t
print(f"      Done: {t:.2f}s\n")

# --- Method 4: Async ---
print(f"[4/4] Running ASYNC (aiohttp)...")
from bench_async import run as run_async
t = run_async(patients)
results["Async (aiohttp)"] = t
print(f"      Done: {t:.2f}s\n")

# --- Results Table ---
baseline = results["Sequential"]
print("=" * 70)
print(f"{'Method':<20} {'Time (30 pts)':<16} {'Per patient':<14} {'300 pts est.':<14} {'Speedup'}")
print("-" * 70)
for method, elapsed in results.items():
    per_patient = elapsed / n
    projected_min = per_patient * 300 / 60
    speedup = baseline / elapsed
    print(f"{method:<20} {elapsed:>8.2f}s      {per_patient:>6.2f}s/pt     {projected_min:>5.1f} min      {speedup:.1f}x")

best = min(results, key=results.get)
print("=" * 70)
print(f"\nWINNER: {best} ({results[best]:.2f}s for {n} patients)")
print(f"        Projected: {results[best]/n*300/60:.1f} minutes for all 300 patients")
