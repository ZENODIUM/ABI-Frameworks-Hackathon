"""
Streamlit dashboard for wound care billing routing decisions.
Run: streamlit run app.py
"""

import os
import sqlite3
import pandas as pd
import streamlit as st

_HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_HERE, "abi.db")
OUTPUT_CSV = os.path.join(_HERE, "output.csv")

st.set_page_config(
    page_title="Wound Care Billing Dashboard",
    page_icon="🏥",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Load data helpers
# ---------------------------------------------------------------------------

@st.cache_data(ttl=60)
def load_output() -> pd.DataFrame | None:
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("SELECT * FROM eligibility_output", conn)
        conn.close()
        return df
    except Exception:
        try:
            return pd.read_csv(OUTPUT_CSV)
        except Exception:
            return None


@st.cache_data(ttl=60)
def load_table(table: str) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
    conn.close()
    return df


@st.cache_data(ttl=60)
def load_notes_for_patient(patient_id: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            """SELECT n.note_type, n.effective_date, n.note_text, n.created_by
               FROM notes n
               JOIN patients p ON n.patient_id = p.id
               WHERE p.patient_id = ? AND n.is_current = 1
               ORDER BY n.effective_date DESC""",
            (patient_id,)
        )
        rows = cur.fetchall()
        conn.close()
        return rows
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Routing color helpers
# ---------------------------------------------------------------------------

ROUTING_COLOR = {
    "auto_accept":    "#1a7a4a",
    "flag_for_review":"#b07d00",
    "reject":         "#c0392b",
}
ROUTING_BG = {
    "auto_accept":    "#d4edda",
    "flag_for_review":"#fff3cd",
    "reject":         "#f8d7da",
}
ROUTING_EMOJI = {
    "auto_accept":    "✅",
    "flag_for_review":"⚠️",
    "reject":         "❌",
}
ROUTING_LABEL = {
    "auto_accept":    "Auto Accept",
    "flag_for_review":"Flag for Review",
    "reject":         "Reject",
}

def color_routing(val):
    color = ROUTING_COLOR.get(val, "#333")
    bg    = ROUTING_BG.get(val, "#fff")
    return f"background-color: {bg}; color: {color}; font-weight: bold;"


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.title("Wound Care Billing — Patient Routing Dashboard")
st.caption("Medicare Part B wound care eligibility pipeline | ABI Frameworks Hackathon")

df = load_output()

if df is None:
    st.error("No data found. Run: `python pipeline.py`")
    st.stop()

df["has_medicare_b"] = df["has_medicare_b"].astype(bool)
df["has_wound_dx"]   = df["has_wound_dx"].astype(bool)
facility_map = {101: "Facility A (101)", 102: "Facility B (102)", 103: "Facility C (103)"}
df["facility_label"] = df["facility_id"].map(facility_map).fillna(df["facility_id"].astype(str))

# ---------------------------------------------------------------------------
# Summary metrics (always visible at top)
# ---------------------------------------------------------------------------

total       = len(df)
auto_accept = int((df["routing"] == "auto_accept").sum())
flag        = int((df["routing"] == "flag_for_review").sum())
reject      = int((df["routing"] == "reject").sum())
mcb_count   = int(df["has_medicare_b"].sum())

st.markdown("---")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total Patients",    total)
c2.metric("✅ Auto Accept",    auto_accept)
c3.metric("⚠️ Flag for Review", flag)
c4.metric("❌ Reject",         reject)
c5.metric("Medicare Part B",   mcb_count)
st.markdown("---")

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab1, tab2, tab3 = st.tabs(["📋 Billing Dashboard", "🔍 Patient Detail", "🗄️ Raw Data Explorer"])


# ============================================================
# TAB 1 — Billing Dashboard
# ============================================================
with tab1:

    # Sidebar filters
    st.sidebar.header("Filters")
    selected_routing = st.sidebar.multiselect(
        "Routing Decision",
        options=["auto_accept", "flag_for_review", "reject"],
        default=["auto_accept", "flag_for_review", "reject"],
    )
    facility_options = df["facility_label"].unique().tolist()
    selected_facilities = st.sidebar.multiselect(
        "Facility", options=facility_options, default=facility_options,
    )
    wound_types = ["All"] + sorted(df["wound_type"].dropna().unique().tolist())
    selected_wound_type = st.sidebar.selectbox("Wound Type", options=wound_types)
    mcb_only = st.sidebar.checkbox("Medicare Part B only", value=False)

    # Apply filters
    filtered = df.copy()
    if selected_routing:
        filtered = filtered[filtered["routing"].isin(selected_routing)]
    if selected_facilities:
        filtered = filtered[filtered["facility_label"].isin(selected_facilities)]
    if selected_wound_type != "All":
        filtered = filtered[filtered["wound_type"] == selected_wound_type]
    if mcb_only:
        filtered = filtered[filtered["has_medicare_b"]]

    st.markdown(f"**Showing {len(filtered)} of {total} patients**")

    display_cols = [
        "patient_id", "name", "facility_label", "routing",
        "wound_type", "stage", "location",
        "length_cm", "width_cm", "depth_cm", "drainage_amount",
        "has_medicare_b", "has_wound_dx", "extraction_source", "reason",
    ]
    table_df = filtered[display_cols].rename(columns={
        "patient_id": "Patient ID", "name": "Name", "facility_label": "Facility",
        "routing": "Routing", "wound_type": "Wound Type", "stage": "Stage",
        "location": "Location", "length_cm": "Length (cm)", "width_cm": "Width (cm)",
        "depth_cm": "Depth (cm)", "drainage_amount": "Drainage",
        "has_medicare_b": "Medicare B", "has_wound_dx": "Wound Dx",
        "extraction_source": "Data Source", "reason": "Decision Reason",
    })
    styled = table_df.style.map(color_routing, subset=["Routing"])
    st.dataframe(styled, use_container_width=True, height=500)

    csv_bytes = filtered.to_csv(index=False).encode("utf-8")
    st.download_button("Download filtered results as CSV", csv_bytes,
                       "wound_billing_output.csv", "text/csv")

    # Facility breakdown chart
    st.markdown("---")
    st.subheader("Routing Breakdown by Facility")
    pivot = (
        df.groupby(["facility_label", "routing"]).size()
        .unstack(fill_value=0).reset_index()
    )
    if not pivot.empty:
        st.bar_chart(pivot.set_index("facility_label"))


# ============================================================
# TAB 2 — Patient Detail
# ============================================================
with tab2:
    st.subheader("Patient Detail")
    patient_ids = [""] + sorted(df["patient_id"].tolist())
    selected_pid = st.selectbox("Select a Patient ID", options=patient_ids)

    if selected_pid:
        row = df[df["patient_id"] == selected_pid].iloc[0]
        routing = row["routing"]
        color = ROUTING_COLOR.get(routing, "#333")
        bg    = ROUTING_BG.get(routing, "#eee")

        st.markdown(
            f"""<div style="background:{bg}; border-left:5px solid {color};
                padding:12px 18px; border-radius:6px; margin-bottom:12px;">
              <h3 style="color:{color}; margin:0">
                {ROUTING_EMOJI.get(routing,'')} {ROUTING_LABEL.get(routing, routing)}
              </h3>
              <p style="margin:4px 0 0 0; color:#333">{row['reason']}</p>
            </div>""",
            unsafe_allow_html=True,
        )

        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.markdown("**Patient Info**")
            st.write(f"Name: {row['name']}")
            st.write(f"Facility: {row['facility_label']}")
            st.write(f"Primary Payer: {row['primary_payer']}")
            st.write(f"Medicare Part B: {'Yes' if row['has_medicare_b'] else 'No'}")
            st.write(f"Wound Diagnosis: {'Yes' if row['has_wound_dx'] else 'No'}")
            if row.get("wound_dx_codes"):
                st.write(f"ICD-10 Codes: {row['wound_dx_codes']}")
        with col_b:
            st.markdown("**Wound Data Extracted**")
            st.write(f"Type: {row.get('wound_type') or 'Not found'}")
            st.write(f"Stage: {row.get('stage') or 'N/A'}")
            st.write(f"Location: {row.get('location') or 'Not found'}")
            st.write(f"Drainage: {row.get('drainage_amount') or 'Not found'}")
        with col_c:
            st.markdown("**Measurements**")
            st.write(f"Length: {row.get('length_cm') or 'Missing'} cm")
            st.write(f"Width:  {row.get('width_cm')  or 'Missing'} cm")
            st.write(f"Depth:  {row.get('depth_cm')  or 'Missing'} cm")
            st.write(f"Data source: {row.get('extraction_source', 'none')}")

        st.markdown("**Clinical Notes**")
        notes = load_notes_for_patient(selected_pid)
        if notes:
            for note_type, eff_date, note_text, created_by in notes:
                with st.expander(f"{note_type or 'Note'} — {eff_date or ''} — {created_by or ''}"):
                    st.text(note_text or "(empty)")
        else:
            st.info("No clinical notes found.")


# ============================================================
# TAB 3 — Raw Data Explorer
# ============================================================
with tab3:
    st.subheader("Raw Data Explorer")
    st.caption("Browse all tables fetched from the PCC API — unmodified.")

    TABLE_DESCRIPTIONS = {
        "patients":           "All 300 patients. Contains patient_id (string) and id (integer).",
        "diagnoses":          "ICD-10 codes per patient. clinical_status = active/resolved/inactive.",
        "coverage":           "Insurance coverage records. payer_code MCB = Medicare Part B. effective_to=null means active.",
        "notes":              "Free-text clinical progress notes. note_text is the raw nurse note.",
        "assessments":        "Structured wound assessment forms. raw_json has pre-parsed measurements.",
        "eligibility_output": "Final output — one row per patient with routing decision and wound fields.",
        "sync_state":         "Last successful sync timestamp for incremental sync.",
    }

    selected_table = st.selectbox("Select table", list(TABLE_DESCRIPTIONS.keys()), index=0)
    st.info(TABLE_DESCRIPTIONS[selected_table])

    raw_df = load_table(selected_table)
    st.markdown(f"**{len(raw_df)} rows, {len(raw_df.columns)} columns**")

    if selected_table == "notes":
        search = st.text_input("Search note text")
        if search:
            raw_df = raw_df[raw_df["note_text"].str.contains(search, case=False, na=False)]
            st.markdown(f"**{len(raw_df)} matching notes**")
        for _, r in raw_df.iterrows():
            with st.expander(f"Patient {r['patient_id']} | {r['note_type']} | {r['effective_date']}"):
                st.text(r["note_text"] or "(empty)")

    elif selected_table == "assessments":
        for _, r in raw_df.iterrows():
            with st.expander(f"Patient {r['patient_id']} | {r['assessment_type']} | {r['assessment_date']}"):
                st.code(r["raw_json"] or "(empty)", language="json")

    else:
        search = st.text_input("Filter rows (searches all columns)")
        if search:
            mask = raw_df.apply(lambda col: col.astype(str).str.contains(search, case=False, na=False)).any(axis=1)
            raw_df = raw_df[mask]
            st.markdown(f"**{len(raw_df)} matching rows**")
        st.dataframe(raw_df, use_container_width=True, height=550)
        st.download_button(
            f"Download {selected_table}.csv",
            raw_df.to_csv(index=False).encode("utf-8"),
            f"{selected_table}.csv", "text/csv"
        )
