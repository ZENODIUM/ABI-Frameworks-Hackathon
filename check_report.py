"""One-off report of all validation checks and outcomes."""
import sqlite3

conn = sqlite3.connect("abi.db")
cur = conn.cursor()

print("=" * 60)
print("FINAL ROUTING")
print("=" * 60)
cur.execute("SELECT routing, COUNT(*) FROM eligibility_output GROUP BY routing")
for r, n in cur.fetchall():
    print(f"  {r}: {n}")

print("\n" + "=" * 60)
print("AMBIGUITY FLAGS (patients with non-empty flags)")
print("=" * 60)
cur.execute(
    "SELECT patient_id, ambiguity_flags FROM eligibility_output "
    "WHERE ambiguity_flags IS NOT NULL AND ambiguity_flags != ''"
)
rows = cur.fetchall()
print(f"  Total: {len(rows)}")
for pid, flags in rows:
    print(f"  {pid}: {flags}")

print("\n" + "=" * 60)
print("FLAG_FOR_REVIEW — full breakdown")
print("=" * 60)
cur.execute(
    "SELECT patient_id, reason, ambiguity_flags FROM eligibility_output "
    "WHERE routing = 'flag_for_review'"
)
for pid, reason, af in cur.fetchall():
    print(f"\n  {pid}")
    if af:
        print(f"    ambiguity: {af}")
    print(f"    {reason}")

print("\n" + "=" * 60)
print("REJECT breakdown")
print("=" * 60)
cur.execute(
    "SELECT COUNT(*) FROM eligibility_output WHERE routing='reject' AND has_medicare_b=0"
)
print(f"  No Medicare B: {cur.fetchone()[0]}")
cur.execute(
    "SELECT COUNT(*) FROM eligibility_output WHERE routing='reject' AND has_medicare_b=1"
)
print(f"  Has Medicare B but rejected: {cur.fetchone()[0]}")

conn.close()
