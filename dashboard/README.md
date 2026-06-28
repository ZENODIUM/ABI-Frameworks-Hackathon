# Wound Route Dashboard

React dashboard for billing routing decisions (replaces basic Streamlit for presentation).

## Quick start

```bash
# 1. Run pipeline (if not done)
python pipeline.py --skip-ingest --use-llm

# 2. Export data to JSON
python export_dashboard_data.py

# 3. Start Gemini summary API (separate terminal)
$env:GEMINI_API_KEY="your-key"
python dashboard_api.py

# 4. Start dashboard
cd dashboard
npm install
npm run dev
```

Open http://localhost:5173

## Features

- **Traffic lights** — green / yellow / red routing; on patient select only matching light glows
- **Patient card** — click row → full center overlay with all fields + Gemini AI summary (closable)
- **Search** — real-time filter
- **Toggle filters** — hard gates, completeness, ambiguities
- **Analytics** — soft palette, big stat numbers, pipeline mindmap SVG

## Production build

```bash
npm run build
npm run preview
```

Re-run `python export_dashboard_data.py` after each pipeline run to refresh data.
