# Wound Route

Automated wound care billing eligibility for skilled nursing facilities. Ingests 300 synthetic patients from the PCC mock API, extracts wound fields from clinical documentation, applies Medicare Part B routing rules, and surfaces results in a React dashboard.

---

## Problem

Billers must decide per patient:

- Is **Medicare Part B** active?
- Is there **documented wound care** with complete measurements?
- Should the claim be **submitted**, **reviewed**, or **rejected**?

Manual review of notes, assessments, diagnoses, and coverage across 300 patients is slow and error-prone.

---

## Solution Overview

```
PCC API (300 patients)
    → ingestion.py       (async fetch + SQLite)
    → extraction.py      (regex: assessments first, notes second)
    → llm_extraction.py  (optional Gemini gap-fill)
    → eligibility.py     (3-layer routing)
    → output.csv + dashboard (Wound Route UI)
```

---

## Architecture & Design Choices

| Choice | Why |
|--------|-----|
| **Async ingestion** (`aiohttp`) | ~47s for 300 patients vs ~8 min threads; handles 30% API 429 rate limits with `Retry-After` |
| **Regex-first extraction** | Assessments are structured; notes use predictable patterns (SOAP, Envive, prose). Fast, auditable, no API cost |
| **Assessments > notes priority** | Structured forms are more reliable; notes only fill gaps |
| **Gemini optional (`--use-llm`)** | Recovers ~14 edge cases (stage from ICD, location from narrative) without overwriting regex values |
| **3-layer routing** | Mirrors real billing: insurance gate → completeness → cross-source validation |
| **React dashboard** | Traffic-light UX, filters per rule, patient cards with Gemini biller summaries |
| **API key server-side** | `dashboard_api.py` keeps Gemini key out of the browser |

---

## Quick Start

```bash
# Install Python dependencies
pip install -r requirements.txt

# Full pipeline (first time — fetches from PCC API)
python pipeline.py

# Re-run without re-fetching API (+ optional Gemini gap-fill)
python pipeline.py --skip-ingest --use-llm

# Export JSON for dashboard
python export_dashboard_data.py

# Terminal 1 — Gemini summaries (create .env from .env.example first)
python dashboard_api.py

# Terminal 2 — Dashboard UI
cd dashboard
npm install
npm run dev
# → http://localhost:5173
```

Or use `.\start_local.ps1` (Windows) to launch API + dashboard in separate windows.

---

## Step 1 — Ingestion (`ingestion.py`)

**What:** Fetch all PCC data into `abi.db`. No clinical logic — raw storage only.

| Endpoint | ID type | Table |
|----------|---------|-------|
| `/pcc/patients` | facility | `patients` |
| `/pcc/diagnoses` | string `patient_id` (FA-001) | `diagnoses` |
| `/pcc/coverage` | string `patient_id` | `coverage` |
| `/pcc/notes` | integer `id` | `notes` |
| `/pcc/assessments` | integer `id` | `assessments` |

**Rate limiting:** ~30% of requests return HTTP 429. Retries use the server's `Retry-After` header (up to 8 attempts).

**Bonus:** `--incremental` sync via `sync_state` table — only fetches records modified since last run.

---

## Step 2 — Extraction (`extraction.py`)

**What:** Pull billing fields from assessments and notes using **regex only**.

### Fields extracted

| Field | Source patterns |
|-------|-----------------|
| `wound_type` | pressure ulcer, diabetic, venous, surgical, abscess, burn, arterial |
| `location` | "to Right hip /", "at Right cervical wound site", ICD descriptions |
| `length_cm`, `width_cm`, `depth_cm` | `3.2 x 2.1 x 0.4 cm`, `4.3 cm x 1.8 cm x 0.3 cm`, Envive `Measures 2.9 cm x 2.8 cm`, prose `depth 1.8cm` |
| `drainage_amount` | none / light / moderate / heavy (keyword mapping) |
| `stage` | Stage I–IV, unstageable (pressure ulcers only) |

### Assessment formats

- **Structured Q&A:** `{"question": "Length (cm)", "answer": "5.9"}`
- **Narrative:** `"Pressure Ulcer to Right hip / Measures 2.9 cm x 2.8 cm / Stage: Stage 3"`

### Merge rule

```
For each field: assessment value → else note value → else empty
```

### Multi-wound rule

First measurement in the note = **primary wound**. Secondary wounds (e.g. "heel wound also eval") are ignored.

### Regex-only results

- 300/300 wound types extracted
- ~26 Medicare-B patients still missing required fields before LLM

---

## Step 2b — LLM Gap-Fill (`llm_extraction.py`) — Optional

**When:** `python pipeline.py --use-llm` and `GEMINI_API_KEY` set in environment.

**Who:** Medicare-B patients still missing required fields after regex (typically **26**).

**How:** **2 Gemini API calls**, 14 patients per call, model `gemini-2.5-flash-lite`.

**Rules:**

- Only fills **empty** fields — never overwrites regex/assessment values
- Prompt: "Do not guess measurements"
- Stage may be inferred from ICD text (e.g. "Unstageable Pressure Ulcer" → `unstageable`)
- Does **not** invent depth when Envive notes are 2D-only (`Measures X × Y` with no depth)

**What Gemini recovered (~14 patients):** stage, location from narrative/ICD — not missing depth that is absent in source.

Verify LLM output against source charts:

```bash
python verify_llm_extraction.py --export
```

---

## Step 3 — Eligibility & Routing (`eligibility.py`)

Runs **in order** — first hard gate wins.

### Layer 1 — Hard rejects → `reject`

| Check | Logic | Count |
|-------|-------|-------|
| **No Medicare Part B** | `coverage.payer_code = MCB` AND (`effective_to` is null OR future date) | **155** |
| **Resolved wound dx only** | Wound ICD exists but all are resolved/inactive | **0** in this dataset |
| **No wound evidence** | No active wound dx AND nothing extracted from notes/assessments | **0** on MCB patients |

**155 reject — primary payer breakdown:**

| Payer | Count |
|-------|-------|
| HMO | 63 |
| MCA (Medicare Advantage) | 56 |
| MCD (Medicaid) | 36 |

These patients may have full wound documentation but **wrong billable coverage**.

### Active wound diagnosis (`has_wound_dx`)

True if any diagnosis has:

- `clinical_status = active` (or blank), **and**
- Wound-related ICD prefix (`L89`, `L97`, `L98`, `I83`, `T79`, `T81`) **or** keyword in description (ulcer, abscess, burn, diabetic foot, venous, arterial, etc.)

Examples: `L89.143` Stage 3 Pressure Ulcer ✓ · `Z87.891` resolved history ✗

### Layer 2 — Completeness → `flag_for_review` if missing

**Required for all MCB patients with wound evidence:**

| Field | Required? |
|-------|-----------|
| wound_type | Yes |
| location | Yes |
| length_cm | Yes |
| width_cm | Yes |
| depth_cm | Yes |
| drainage_amount | Yes |
| stage | **Only if pressure ulcer** ("stage trap") |

Burn, diabetic, venous, surgical, arterial, abscess → stage **not** required.

### Layer 3 — Ambiguity → `flag_for_review` even if complete

| Check | Count fired |
|-------|-------------|
| Primary payer vs coverage mismatch | 0 |
| Note vs assessment measurement mismatch (>0.5 cm) | 0 |
| Wound ICD but no clinical docs | 0 |
| Clinical docs but no wound ICD | 0 |
| **Depth > length** (anatomically suspicious) | **2** (FC-005, FC-070) |

### Routing decision tree

```
300 patients
│
├─ Medicare B active?
│    NO  → reject (155)
│    YES → (145 remain)
│         │
│         ├─ Wound dx resolved only?
│         │    YES → reject (0)
│         │    NO  ↓
│         │
│         ├─ Wound evidence? (active dx OR clinical extraction)
│         │    NO  → reject (0 on MCB)
│         │    YES ↓
│         │
│         ├─ All required fields present?
│         │    NO  → flag_for_review
│         │    YES ↓
│         │
│         ├─ Any ambiguity flags?
│         │    YES → flag_for_review
│         │    NO  → auto_accept (131)
```

---

## Final Results (with `--use-llm`)

| Routing | Count | Meaning |
|---------|-------|---------|
| **auto_accept** | **131** | MCB + complete fields + no anomalies → ready to bill |
| **flag_for_review** | **14** | MCB + missing field or anomaly → human review |
| **reject** | **155** | No active Medicare Part B (or other hard gate) |

**Funnel:** 300 → 155 reject → **145 MCB** → 131 accept + 14 flag = 145 ✓

### All 14 flagged patients

| Patient | Why flagged |
|---------|-------------|
| FA-001, FA-005, FA-034, FA-052, FA-057, FA-109, FB-021, FB-027, FB-087, FC-060 | **Missing depth** — Envive 2D format only |
| FB-012, FC-071 | Depth = **0.0 cm** documented; routing treats 0 as empty (known edge case) |
| FC-005, FC-070 | **Depth > length** — verify measurements |

---

## Output Data Dictionary

Each row in `output.csv` / `eligibility_output`:

| Column | Meaning |
|--------|---------|
| `patient_id` | FA-001 style ID |
| `facility_id` | 101 / 102 / 103 |
| `name` | Patient name |
| `primary_payer` | HMO / MCB / MCA / MCD on patient record |
| `has_medicare_b` | Active MCB in coverage table |
| `has_wound_dx` | Active wound-related ICD-10 on file |
| `wound_dx_codes` | Active ICD codes (comma-separated) |
| `wound_type` | Extracted type (pressure_ulcer, venous, etc.) |
| `stage` | Pressure ulcer stage only |
| `location` | Anatomical site |
| `length_cm`, `width_cm`, `depth_cm` | Measurements |
| `drainage_amount` | none / light / moderate / heavy |
| `extraction_source` | assessment / notes / both / both+llm |
| `routing` | auto_accept / flag_for_review / reject |
| `reason` | Plain-English explanation for biller |
| `ambiguity_flags` | Cross-source concerns (if any) |

---

## Dashboard — Wound Route

### Patients tab

- **Traffic lights** — green / yellow / red routing toggles with glow on patient select
- **Search bar** — real-time filter across IDs, names, wounds, reasons
- **Filter pills** — hard gates, completeness, ambiguities (OFF = that criterion not applied)
- **Patient card** — click a row for full detail + Gemini AI biller summary

### Analytics tab

- Big stat numbers, soft palette charts
- **Pipeline mindmap** — 300 → extract → 155 reject → 145 MCB → 131 accept / 14 flag

See `dashboard/README.md` for UI-specific setup.

---

## Project Structure

```
ABI/
├── pipeline.py                 # Orchestrator
├── ingestion.py                # Async API fetch
├── extraction.py               # Regex extraction
├── llm_extraction.py           # Optional Gemini gap-fill
├── eligibility.py              # Routing logic
├── dashboard_api.py            # Gemini patient summaries (server-side)
├── export_dashboard_data.py    # JSON export for React dashboard
├── export_csv.py               # CSV export of all DB tables
├── verify_llm_extraction.py    # Audit LLM fields vs source text
├── app.py                      # Legacy Streamlit dashboard (optional)
├── start_local.ps1             # Launch API + dashboard (Windows)
├── dashboard/                  # React UI (Wound Route)
├── benchmark/                  # Ingestion performance comparisons
├── .env.example                # GEMINI_API_KEY template
└── .gitignore                  # Excludes secrets, abi.db, node_modules
```

---

## Environment Variables

Copy `.env.example` to `.env` (never commit `.env`):

```
GEMINI_API_KEY=your-key-here
DASHBOARD_API_PORT=5001
```

Used by `llm_extraction.py` (pipeline) and `dashboard_api.py` (patient card summaries).

---

## Security

- Never commit `.env`, `abi.db`, API keys, or `exports/`
- `.gitignore` excludes secrets and local patient data
- Rotate any API key that was shared publicly

---

## Other Commands

```bash
python pipeline.py --incremental     # Only fetch changed records
python export_csv.py                 # Dump all tables to exports/
python verify_llm_extraction.py      # Check LLM values against source charts
streamlit run app.py                 # Legacy Streamlit UI
```

---

## 2-Minute Pitch

> "Wound Route ingests 300 patients from three SNFs with async retry on rate limits. Regex extracts wound fields from assessments and notes — SOAP, Envive, and prose formats. Optional Gemini fills gaps without overwriting structured data. Three routing layers: Medicare B gate, field completeness with a stage trap for pressure ulcers, and cross-source validation. **131 ready to bill, 14 for review, 155 correctly rejected.** Billers get traffic-light routing, rule-level filters, and AI summaries per patient."

---

## Hackathon

Built for the **ABI Frameworks** hackathon — PCC mock API wound care billing challenge.
