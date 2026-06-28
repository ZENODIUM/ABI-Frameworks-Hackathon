"""Analyze wound types, stage/location requirements, FA-012."""
import sqlite3
import json
from collections import defaultdict

conn = sqlite3.connect("abi.db")
cur = conn.cursor()

PRESSURE_TYPES = ("pressure_ulcer", "pressure ulcer", "pressure")

def needs_stage(wound_type):
    if not wound_type:
        return False
    return "pressure" in str(wound_type).lower()

cur.execute("""
    SELECT patient_id, wound_type, stage, location, routing, depth_cm,
           length_cm, width_cm, drainage_amount, has_medicare_b
    FROM eligibility_output WHERE has_medicare_b = 1
""")
rows = cur.fetchall()

by_type = defaultdict(lambda: dict(total=0, accept=0, flag=0, no_stage=0, no_loc=0, no_type=0))
for pid, wt, st, loc, rout, dep, ln, wd, dr, mcb in rows:
    key = wt or "(no_type)"
    by_type[key]["total"] += 1
    if rout == "auto_accept":
        by_type[key]["accept"] += 1
    if rout == "flag_for_review":
        by_type[key]["flag"] += 1
    if not wt:
        by_type[key]["no_type"] += 1
    if needs_stage(wt) and (st is None or st == ""):
        by_type[key]["no_stage"] += 1
    if not loc:
        by_type[key]["no_loc"] += 1

print("MCB PATIENTS BY WOUND TYPE")
print("-" * 70)
for wt, d in sorted(by_type.items(), key=lambda x: -x[1]["total"]):
    req_stage = "YES" if needs_stage(wt) else "no"
    print(f"  {wt:<30} n={d['total']:3} accept={d['accept']:3} flag={d['flag']:3} "
          f"missing_stage={d['no_stage']:3} missing_loc={d['no_loc']:3} stage_req={req_stage}")

print("\nPRESSURE ULCER WITHOUT STAGE (MCB):")
cur.execute("""
    SELECT patient_id, stage, location, routing FROM eligibility_output
    WHERE has_medicare_b=1 AND wound_type LIKE '%pressure%'
    AND (stage IS NULL OR stage = '')
""")
for r in cur.fetchall():
    print(f"  {r}")

print("\nAUTO_ACCEPT MISSING LOCATION:")
cur.execute("""
    SELECT patient_id, wound_type, location FROM eligibility_output
    WHERE routing='auto_accept' AND (location IS NULL OR location = '')
""")
for r in cur.fetchall():
    print(f"  {r}")

print("\nAUTO_ACCEPT MISSING WOUND TYPE:")
cur.execute("""
    SELECT patient_id, wound_type, routing FROM eligibility_output
    WHERE routing='auto_accept' AND (wound_type IS NULL OR wound_type = '')
""")
for r in cur.fetchall():
    print(f"  {r}")

print("\nFLAG_FOR_REVIEW FIELD GAPS:")
cur.execute("""
    SELECT patient_id, wound_type, stage, location, depth_cm, reason
    FROM eligibility_output WHERE routing='flag_for_review'
""")
for pid, wt, st, loc, dep, reason in cur.fetchall():
    gaps = []
    if not wt:
        gaps.append("wound_type")
    if needs_stage(wt) and (st is None or st == ""):
        gaps.append("stage")
    if not loc:
        gaps.append("location")
    if dep is None:
        gaps.append("depth")
    print(f"  {pid}: gaps={gaps}")

print("\nFA-012 NOTES (why 2 notes?):")
cur.execute("""
    SELECT n.id, n.note_type, n.effective_date, n.note_text
    FROM notes n JOIN patients p ON n.patient_id = p.id
    WHERE p.patient_id = 'FA-012' AND n.is_current = 1
""")
for nid, ntype, edate, text in cur.fetchall():
    print(f"\n  note_id={nid} | {ntype} | {edate}")
    print(text)

cur.execute("""
    SELECT raw_json FROM assessments a JOIN patients p ON a.patient_id = p.id
    WHERE p.patient_id = 'FA-012' AND a.is_current = 1
""")
for (rj,) in cur.fetchall():
    print("\nFA-012 ASSESSMENT:")
    print(rj[:800])

cur.execute("""
    SELECT wound_type, stage, location, length_cm, width_cm, depth_cm, drainage_amount, routing
    FROM eligibility_output WHERE patient_id = 'FA-012'
""")
print("\nFA-012 OUTPUT:", cur.fetchone())

conn.close()
