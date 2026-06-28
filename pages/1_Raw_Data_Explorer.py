"""
Raw Data Explorer — browse all tables in abi.db as-is.
Accessible from the Streamlit sidebar as a second page.
"""

import sqlite3
import pandas as pd
import streamlit as st

import os
_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # parent of pages/
DB_PATH = os.path.join(_HERE, "abi.db")

st.set_page_config(page_title="Raw Data Explorer", layout="wide")
st.title("Raw Data Explorer")
st.caption("Browse all raw data fetched from the PCC API — unmodified.")

@st.cache_data(ttl=60)
def load_table(table: str) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
    conn.close()
    return df

TABLE_DESCRIPTIONS = {
    "patients":           "All 300 patients across 3 facilities. Contains both patient_id (string) and id (integer).",
    "diagnoses":          "ICD-10 diagnosis codes per patient. Multiple rows per patient. clinical_status = active/resolved/inactive.",
    "coverage":           "Insurance coverage records. payer_code MCB = Medicare Part B (what we care about). effective_to=null means still active.",
    "notes":              "Free-text clinical progress notes. note_text is the raw nurse note used for wound extraction.",
    "assessments":        "Structured wound assessment forms. raw_json contains pre-parsed wound measurements.",
    "eligibility_output": "Final output table — one row per patient with routing decision and extracted wound fields.",
    "sync_state":         "Tracks last successful sync timestamp for incremental sync feature.",
}

table = st.sidebar.selectbox(
    "Select table",
    list(TABLE_DESCRIPTIONS.keys()),
    index=5,  # default to eligibility_output
)

st.subheader(f"Table: `{table}`")
st.info(TABLE_DESCRIPTIONS[table])

df = load_table(table)
st.markdown(f"**{len(df)} rows, {len(df.columns)} columns**")

# Special handling for notes — show note_text in expander to keep table readable
if table == "notes":
    search = st.text_input("Search note text", "")
    if search:
        df = df[df["note_text"].str.contains(search, case=False, na=False)]
        st.markdown(f"**{len(df)} matching notes**")

    for _, row in df.iterrows():
        with st.expander(f"Patient ID {row['patient_id']} | {row['note_type']} | {row['effective_date']}"):
            st.text(row["note_text"] or "(empty)")

elif table == "assessments":
    for _, row in df.iterrows():
        with st.expander(f"Patient ID {row['patient_id']} | {row['assessment_type']} | {row['assessment_date']}"):
            st.code(row["raw_json"] or "(empty)", language="json")

else:
    # Column filter
    all_cols = df.columns.tolist()
    selected_cols = st.multiselect("Columns to show", all_cols, default=all_cols)
    if selected_cols:
        df = df[selected_cols]

    # Row search for string tables
    search = st.text_input("Filter rows (searches all text columns)", "")
    if search:
        mask = df.apply(lambda col: col.astype(str).str.contains(search, case=False, na=False)).any(axis=1)
        df = df[mask]
        st.markdown(f"**{len(df)} matching rows**")

    st.dataframe(df, use_container_width=True, height=600)

    # Download
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(f"Download {table}.csv", csv, f"{table}.csv", "text/csv")
