"""
Quick database analysis — run once to inspect data quality.
"""
import sqlite3

conn = sqlite3.connect("abi.db")
cur = conn.cursor()

print("=" * 55)
print("DATABASE ROW COUNTS")
print("=" * 55)
for t in ["patients", "diagnoses", "coverage", "notes", "assessments", "eligibility_output", "sync_state"]:
    cur.execute(f"SELECT COUNT(*) FROM {t}")
    print(f"  {t:<22} {cur.fetchone()[0]:>5} rows")

print()
print("=" * 55)
print("ROUTING DECISIONS")
print("=" * 55)
cur.execute("SELECT routing, COUNT(*) FROM eligibility_output GROUP BY routing")
for row in cur.fetchall():
    print(f"  {row[0]:<20} {row[1]:>5}")

print()
print("=" * 55)
print("EXTRACTION SOURCE")
print("=" * 55)
cur.execute("SELECT extraction_source, COUNT(*) FROM eligibility_output GROUP BY extraction_source")
for row in cur.fetchall():
    print(f"  source={row[0]:<15} {row[1]:>5}")

print()
print("=" * 55)
print("MISSING FIELDS (all 300 patients)")
print("=" * 55)
cur.execute("""
    SELECT
        SUM(CASE WHEN wound_type='' OR wound_type IS NULL THEN 1 ELSE 0 END),
        SUM(CASE WHEN length_cm IS NULL THEN 1 ELSE 0 END),
        SUM(CASE WHEN width_cm IS NULL THEN 1 ELSE 0 END),
        SUM(CASE WHEN depth_cm IS NULL THEN 1 ELSE 0 END),
        SUM(CASE WHEN drainage_amount='' OR drainage_amount IS NULL THEN 1 ELSE 0 END),
        SUM(CASE WHEN location='' OR location IS NULL THEN 1 ELSE 0 END)
    FROM eligibility_output
""")
r = cur.fetchone()
fields = ["wound_type", "length_cm", "width_cm", "depth_cm", "drainage_amount", "location"]
for field, count in zip(fields, r):
    bar = "#" * count
    print(f"  missing {field:<18} {count:>3}  {bar}")

print()
print("=" * 55)
print("WOUND TYPE DISTRIBUTION")
print("=" * 55)
cur.execute("""
    SELECT wound_type, COUNT(*) as n FROM eligibility_output
    WHERE wound_type != '' AND wound_type IS NOT NULL
    GROUP BY wound_type ORDER BY n DESC
""")
for row in cur.fetchall():
    print(f"  {row[0]:<35} {row[1]:>4}")

print()
print("=" * 55)
print("PAYER MIX")
print("=" * 55)
cur.execute("SELECT primary_payer, COUNT(*) as n FROM eligibility_output GROUP BY primary_payer ORDER BY n DESC")
for row in cur.fetchall():
    print(f"  {row[0]:<10} {row[1]:>4}")

print()
print("=" * 55)
print("ANOMALIES / DATA QUALITY ISSUES")
print("=" * 55)

# Patients with Medicare B but NO wound evidence at all
cur.execute("""
    SELECT COUNT(*) FROM eligibility_output
    WHERE has_medicare_b=1 AND extraction_source='none' AND has_wound_dx=0
""")
print(f"  MCB patients with zero wound evidence:    {cur.fetchone()[0]}")

# Patients with wound data but no Medicare B
cur.execute("""
    SELECT COUNT(*) FROM eligibility_output
    WHERE has_medicare_b=0 AND extraction_source != 'none'
""")
print(f"  Has wound data but no Medicare B:         {cur.fetchone()[0]}")

# Patients with measurements but impossible values (e.g. > 30cm)
cur.execute("""
    SELECT patient_id, wound_type, length_cm, width_cm, depth_cm FROM eligibility_output
    WHERE length_cm > 30 OR width_cm > 30 OR depth_cm > 15
""")
outliers = cur.fetchall()
print(f"  Suspicious measurement outliers (>30cm):  {len(outliers)}")
for row in outliers:
    print(f"    {row[0]}  {row[1]}  {row[2]}x{row[3]}x{row[4]} cm")

# Patients where depth > length (anatomically odd)
cur.execute("""
    SELECT patient_id, length_cm, width_cm, depth_cm FROM eligibility_output
    WHERE depth_cm IS NOT NULL AND length_cm IS NOT NULL AND depth_cm > length_cm
""")
odd = cur.fetchall()
print(f"  Depth > length (unusual anatomy):         {len(odd)}")
for row in odd:
    print(f"    {row[0]}  {row[1]}x{row[2]}x{row[3]} cm")

# Patients with no notes AND no assessments at all
cur.execute("""
    SELECT COUNT(*) FROM patients p
    WHERE NOT EXISTS (SELECT 1 FROM notes n WHERE n.patient_id=p.id)
    AND NOT EXISTS (SELECT 1 FROM assessments a WHERE a.patient_id=p.id)
""")
print(f"  Patients with no notes AND no assessments: {cur.fetchone()[0]}")

# flag_for_review — what's most commonly missing
print()
print("=" * 55)
print("FLAG_FOR_REVIEW — What fields are most commonly missing")
print("=" * 55)
cur.execute("""
    SELECT reason FROM eligibility_output WHERE routing='flag_for_review'
""")
from collections import Counter
missing_counts = Counter()
for (reason,) in cur.fetchall():
    if "missing:" in reason:
        parts = reason.split("missing:")[1].split(".")[0].strip()
        for field in parts.split(","):
            missing_counts[field.strip()] += 1
for field, count in missing_counts.most_common():
    print(f"  {field:<25} {count:>4}")

print()
print("=" * 55)
print("SAMPLE auto_accept patients")
print("=" * 55)
cur.execute("""
    SELECT patient_id, name, wound_type, length_cm, width_cm, depth_cm, drainage_amount
    FROM eligibility_output WHERE routing='auto_accept' LIMIT 5
""")
for row in cur.fetchall():
    print(f"  {row[0]}  {row[1]:<20}  {row[2]:<25}  {row[3]}x{row[4]}x{row[5]} cm  drainage={row[6]}")

print()
print("=" * 55)
print("SAMPLE reject patients")
print("=" * 55)
cur.execute("""
    SELECT patient_id, name, primary_payer, reason
    FROM eligibility_output WHERE routing='reject' LIMIT 5
""")
for row in cur.fetchall():
    print(f"  {row[0]}  {row[1]:<20}  payer={row[2]}  {row[3][:60]}")

conn.close()
