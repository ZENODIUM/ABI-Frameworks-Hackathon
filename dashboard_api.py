"""
Lightweight API for Gemini patient summaries (keeps API key server-side).
Run alongside dashboard: python dashboard_api.py
"""

import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "abi.db"
PORT = int(os.environ.get("DASHBOARD_API_PORT", "5001"))
GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)


def _clinical_context(patient_id: str) -> str:
    if not DB_PATH.exists():
        return ""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    parts = []
    for code, desc, status in cur.execute(
        "SELECT icd10_code, icd10_description, clinical_status FROM diagnoses WHERE patient_id=?",
        (patient_id,),
    ):
        parts.append(f"DX {code} ({status}): {desc}")
    iid = cur.execute("SELECT id FROM patients WHERE patient_id=?", (patient_id,)).fetchone()
    if iid:
        for raw in cur.execute(
            "SELECT raw_json FROM assessments WHERE patient_id=? AND is_current=1 LIMIT 2",
            (iid[0],),
        ):
            parts.append((raw[0] or "")[:1200])
        for text in cur.execute(
            "SELECT note_text FROM notes WHERE patient_id=? AND is_current=1 LIMIT 2",
            (iid[0],),
        ):
            parts.append((text[0] or "")[:800])
    conn.close()
    return "\n".join(parts)


def _summarize(patient: dict) -> str:
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")

    pid = patient.get("patient_id", "")
    clinical = _clinical_context(pid)
    prompt = f"""You are a wound care billing assistant. Write a concise 3-4 sentence summary for a biller about this patient.
Explain: insurance eligibility, wound documentation status, routing decision, and what action is needed (if any).
Be factual — only use data below. No markdown.

PATIENT RECORD:
{json.dumps(patient, indent=2)}

CLINICAL SOURCE (excerpt):
{clinical or '(not loaded)'}
"""
    resp = requests.post(
        GEMINI_URL,
        params={"key": key},
        json={
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 256},
        },
        timeout=45,
    )
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if urlparse(self.path).path == "/api/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.end_headers()
            has_key = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
            self.wfile.write(json.dumps({"ok": True, "gemini_configured": has_key}).encode())
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if urlparse(self.path).path != "/api/summarize":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        patient = body.get("patient") or {}
        try:
            summary = _summarize(patient)
            payload = {"summary": summary}
            code = 200
        except Exception as e:
            payload = {"error": str(e)}
            code = 500
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    def log_message(self, fmt, *args):
        print(f"[dashboard_api] {args[0]}")


if __name__ == "__main__":
    print(f"Dashboard API http://localhost:{PORT}  (GEMINI_API_KEY required for summaries)")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
