# app.py
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import random
import re
import requests
import json
import time
from urllib.parse import quote

# Page Configuration
st.set_page_config(
    page_title="CarePilot AI - Healthcare Automation",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ================================================
# N8N WEBHOOK CONFIGURATION
# ================================================
N8N_WEBHOOK_URL = "http://localhost:5678/webhook-test/carepilot-ai"
N8N_FOLLOWUP_URL = "http://localhost:5678/webhook-test/carepilot-followups"

# ================================================
# GOOGLE SHEETS CONFIGURATION
# ================================================
SPREADSHEET_ID = "1OpQ9y0_O3Qho15DjfR-lzp0uuFS5AnM5xPlmgLngKgs"
SHEET_TABS = {
    "patients": "Patients",
    "appointments": "Appointments",
    "queries": "Queries",
}

def _sheet_csv_url(sheet_name: str) -> str:
    """Generate CSV export URL with cache-buster to always fetch fresh data."""
    cache_buster = int(time.time())
    return (
        f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}"
        f"/gviz/tq?tqx=out:csv&sheet={quote(sheet_name)}"
        f"&_={cache_buster}"
    )

def fetch_sheet_df(sheet_key: str) -> pd.DataFrame:
    """
    Fetch a tab from the CarePilot Google Sheet as a DataFrame.
    Always fetches fresh data (no caching) so dashboard shows latest updates.
    Returns an empty DataFrame (never raises) so the dashboard
    degrades gracefully if the sheet isn't shared publicly yet.
    """
    sheet_name = SHEET_TABS.get(sheet_key, sheet_key)
    try:
        url = _sheet_csv_url(sheet_name)
        df = pd.read_csv(url)
        df.columns = [str(c).strip() for c in df.columns]
        return df
    except Exception:
        return pd.DataFrame()

# ================================================
# SEQUENTIAL ID GENERATORS
# ================================================

def get_next_patient_id() -> str:
    """
    Reads the last Patient ID from Google Sheets and returns the next sequential ID.
    Format: CP-YYYY-XXXX (e.g., CP-2026-0042)
    """
    df = fetch_sheet_df("patients")
    if df.empty or "Patient ID" not in df.columns:
        return f"CP-{datetime.now().year}-0001"
    
    ids = df["Patient ID"].astype(str).str.extract(r'CP-\d{4}-(\d+)')[0]
    ids = pd.to_numeric(ids, errors='coerce').dropna()
    
    next_num = int(ids.max()) + 1 if not ids.empty else 1
    return f"CP-{datetime.now().year}-{next_num:04d}"

def get_next_appt_id() -> str:
    """
    Reads the last Appointment ID from Google Sheets and returns the next sequential ID.
    Format: APT-YYYY-XXXX (e.g., APT-2026-0042)
    """
    df = fetch_sheet_df("appointments")
    if df.empty or "Appt ID" not in df.columns:
        return f"APT-{datetime.now().year}-0001"
    
    ids = df["Appt ID"].astype(str).str.extract(r'APT-\d{4}-(\d+)')[0]
    ids = pd.to_numeric(ids, errors='coerce').dropna()
    
    next_num = int(ids.max()) + 1 if not ids.empty else 1
    return f"APT-{datetime.now().year}-{next_num:04d}"

# ================================================
# DASHBOARD STATS FUNCTIONS
# ================================================

def get_dashboard_stats():
    patients_df = fetch_sheet_df("patients")
    appts_df = fetch_sheet_df("appointments")

    data_available = not patients_df.empty or not appts_df.empty
    total_patients = len(patients_df) if not patients_df.empty else 0

    today_str = datetime.now().strftime("%Y-%m-%d")
    todays_appts = 0
    pending_count = 0
    high_priority_count = 0

    if not appts_df.empty:
        if "Date" in appts_df.columns:
            todays_appts = appts_df["Date"].astype(str).str.strip().eq(today_str).sum()
        if "Status" in appts_df.columns:
            pending_count = appts_df["Status"].astype(str).str.strip().str.lower().eq("pending").sum()
        if "Priority" in appts_df.columns:
            high_priority_count = appts_df["Priority"].astype(str).str.strip().str.lower().isin(
                ["high", "urgent"]
            ).sum()

    stats = [
        ("👤", str(total_patients), "Total Patients", "Live", "up"),
        ("📅", str(int(todays_appts)), "Today's Appointments", "Live", "up"),
        ("⏳", str(int(pending_count)), "Pending Requests", "Live", "down"),
        ("🔴", str(int(high_priority_count)), "High Priority Cases", "Live", "up"),
    ]
    return stats, data_available

def _sorted_tail(df: pd.DataFrame, n: int) -> pd.DataFrame:
    if df.empty:
        return df
    if "Timestamp" in df.columns:
        d = df.copy()
        d["_ts"] = pd.to_datetime(d["Timestamp"], errors="coerce")
        d = d.sort_values("_ts", ascending=False).drop(columns=["_ts"])
        return d.head(n)
    return df.tail(n).iloc[::-1]

def get_recent_patients(limit=6):
    df = fetch_sheet_df("patients")
    if df.empty:
        return []
    df = _sorted_tail(df, limit)
    records = []
    for _, r in df.iterrows():
        records.append({
            "id": r.get("Patient ID", "—"),
            "name": r.get("Name", "Unknown"),
            "age": r.get("Age", "—"),
            "gender": r.get("Gender", "—"),
            "status": str(r.get("Status", "Active")),
            "timestamp": r.get("Timestamp", ""),
        })
    return records

def get_recent_appointments(limit=6):
    df = fetch_sheet_df("appointments")
    if df.empty:
        return []
    df = _sorted_tail(df, limit)
    records = []
    for _, r in df.iterrows():
        records.append({
            "id": r.get("Appt ID", "—"),
            "patient": r.get("Patient", "Unknown"),
            "department": r.get("Department", "—"),
            "priority": str(r.get("Priority", "medium")),
            "date": r.get("Date", "—"),
            "status": str(r.get("Status", "Pending")),
        })
    return records

# ================================================
# CUSTOM CSS - Premium Dark Healthcare Theme
# ================================================
def load_css():
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
        
        * {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            margin: 0; padding: 0; box-sizing: border-box;
        }
        
        /* ── GLOBAL ── */
        .main { background: #080B16; padding: 0rem 1rem; }
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        .stApp {background: #080B16;}
        
        /* ── SIDEBAR ── */
        .css-1d391kg, .css-1lcbmhc {
            background: #0D1020 !important;
            border-right: 1px solid rgba(124, 58, 237, 0.12) !important;
        }
        
        .sidebar-brand {
            padding: 1.8rem 1.5rem 1.5rem 1.5rem;
            border-bottom: 1px solid rgba(124, 58, 237, 0.1);
            margin-bottom: 1.5rem;
        }
        .sidebar-brand h1 {
            font-size: 1.6rem;
            font-weight: 800;
            background: linear-gradient(135deg, #8B5CF6 0%, #A78BFA 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin: 0;
            letter-spacing: -0.5px;
        }
        .sidebar-brand .subtitle {
            font-size: 0.7rem;
            color: #14B8A6;
            letter-spacing: 0.5px;
            font-weight: 400;
            margin-top: 2px;
            -webkit-text-fill-color: #14B8A6;
        }
        
        /* Nav buttons */
        .nav-button {
            display: flex !important; align-items: center !important;
            padding: 0.7rem 1.2rem !important; margin: 0.2rem 0.8rem !important;
            border-radius: 10px !important; color: #94A3B8 !important;
            font-size: 0.85rem !important; font-weight: 500 !important;
            transition: all 0.2s ease !important; cursor: pointer !important;
            text-decoration: none !important; border: 1px solid transparent !important;
            background: transparent !important;
            width: calc(100% - 1.6rem) !important; text-align: left !important;
        }
        .nav-button:hover {
            background: rgba(124, 58, 237, 0.08) !important;
            color: #F8FAFC !important;
            border-color: rgba(124, 58, 237, 0.1) !important;
        }
        .nav-button.active {
            background: rgba(124, 58, 237, 0.12) !important;
            color: #8B5CF6 !important;
            border-color: rgba(124, 58, 237, 0.2) !important;
            box-shadow: 0 4px 15px rgba(124, 58, 237, 0.1) !important;
        }
        .nav-button .nav-icon  { width:1.8rem; font-size:1.1rem; display:inline-block; }
        .nav-button .nav-label { flex:1; display:inline-block; }
        .nav-button .nav-badge {
            font-size:0.6rem; padding:0.1rem 0.5rem; border-radius:12px;
            background:rgba(124,58,237,0.15); color:#8B5CF6;
            display:inline-block; margin-left:0.5rem;
        }
        
        /* Sidebar status */
        .sidebar-status {
            position:fixed; bottom:1.5rem; left:0; width:100%;
            padding:0 1.5rem; border-top:1px solid rgba(124,58,237,0.08);
            padding-top:1rem;
        }
        .status-indicator { display:flex; align-items:center; gap:0.6rem; color:#94A3B8; font-size:0.75rem; }
        .status-dot {
            width:8px; height:8px; border-radius:50%;
            background:#14B8A6;
            animation:pulse-dot 2s infinite;
            box-shadow:0 0 10px rgba(20,184,166,0.3);
        }
        @keyframes pulse-dot {
            0%,100%{opacity:1;transform:scale(1);}
            50%{opacity:0.5;transform:scale(0.9);}
        }
        
        /* ── HEADER ── */
        .app-header { padding:1.2rem 0 0.5rem 0; border-bottom:1px solid rgba(124,58,237,0.06); margin-bottom:1.5rem; }
        .app-header .title   { font-size:1.4rem; font-weight:700; color:#F8FAFC; letter-spacing:-0.5px; }
        .app-header .subtitle{ color:#94A3B8; font-size:0.85rem; font-weight:400; margin-top:2px; }
        .app-header .header-right { text-align:right; color:#94A3B8; font-size:0.75rem; padding-top:0.3rem; }
        .app-header .header-right .status-badge {
            display:inline-flex; align-items:center; gap:0.4rem;
            padding:0.2rem 0.8rem; border-radius:20px;
            background:rgba(20,184,166,0.1); color:#14B8A6; font-size:0.7rem;
        }
        .app-header .header-right .status-badge .dot {
            width:6px; height:6px; border-radius:50%; background:#14B8A6;
        }
        
        /* ── STAT CARDS ── */
        .stat-card {
            position:relative; overflow:hidden;
            background: linear-gradient(155deg, rgba(30,36,64,0.75) 0%, rgba(18,22,42,0.55) 100%);
            backdrop-filter:blur(22px) saturate(150%); -webkit-backdrop-filter:blur(22px) saturate(150%);
            border:1px solid rgba(139,92,246,0.18);
            border-radius:18px; padding:1.3rem 1.3rem 1.1rem 1.3rem;
            transition:all 0.3s cubic-bezier(.2,.8,.2,1); height:100%;
            box-shadow:0 8px 32px rgba(0,0,0,0.25), inset 0 1px 0 rgba(255,255,255,0.06);
        }
        .stat-card::before {
            content:""; position:absolute; top:0; left:0; right:0; height:1px;
            background:linear-gradient(90deg, transparent, rgba(139,92,246,0.6), transparent);
        }
        .stat-card:hover {
            border-color:rgba(139,92,246,0.4);
            transform:translateY(-4px);
            box-shadow:0 16px 40px rgba(124,58,237,0.18), inset 0 1px 0 rgba(255,255,255,0.08);
        }
        .stat-card .stat-icon   { font-size:1.4rem; color:#8B5CF6; margin-bottom:0.3rem; opacity:0.8; }
        .stat-card .stat-number { font-size:2rem; font-weight:700; color:#F8FAFC; line-height:1.2; letter-spacing:-0.5px; }
        .stat-card .stat-label  { font-size:0.8rem; color:#94A3B8; font-weight:400; margin-top:0.1rem; }
        .stat-card .stat-trend  {
            font-size:0.7rem; margin-top:0.4rem; display:inline-flex;
            align-items:center; gap:0.3rem; padding:0.1rem 0.6rem; border-radius:20px;
            background:rgba(20,184,166,0.08); color:#14B8A6;
            border:1px solid rgba(20,184,166,0.1);
        }
        .stat-card .stat-trend.down {
            background:rgba(239,68,68,0.08); color:#F87171;
            border-color:rgba(239,68,68,0.1);
        }
        
        /* ── GLASS CARDS ── */
        .glass-card {
            position:relative; overflow:hidden;
            background:linear-gradient(160deg, rgba(28,34,60,0.6) 0%, rgba(16,20,38,0.4) 100%);
            backdrop-filter:blur(24px) saturate(160%); -webkit-backdrop-filter:blur(24px) saturate(160%);
            border:1px solid rgba(139,92,246,0.14);
            border-radius:18px; padding:1.6rem;
            transition:all 0.3s ease; margin-bottom:1rem;
            box-shadow:0 10px 34px rgba(0,0,0,0.28), inset 0 1px 0 rgba(255,255,255,0.05);
        }
        .glass-card::before {
            content:""; position:absolute; top:0; left:0; right:0; height:1px;
            background:linear-gradient(90deg, transparent, rgba(20,184,166,0.5), transparent);
        }
        .glass-card:hover {
            border-color:rgba(139,92,246,0.28);
            box-shadow:0 14px 38px rgba(124,58,237,0.12), inset 0 1px 0 rgba(255,255,255,0.06);
        }
        .glass-card .card-header {
            display:flex; align-items:center;
            justify-content:space-between; margin-bottom:1rem;
        }
        .glass-card .card-title {
            font-size:0.9rem; font-weight:600; color:#F8FAFC;
            display:flex; align-items:center; gap:0.5rem;
        }
        .glass-card .card-badge {
            font-size:0.6rem; font-weight:500; padding:0.2rem 0.7rem;
            border-radius:20px;
            background:rgba(20,184,166,0.1); color:#14B8A6;
            border:1px solid rgba(20,184,166,0.1);
        }
        
        /* ── FORMS ── */
        .form-container {
            background:rgba(22,28,52,0.4);
            border:1px solid rgba(124,58,237,0.08);
            border-radius:14px; padding:1.5rem;
        }
        .form-container label { color:#94A3B8; font-size:0.8rem; font-weight:500; margin-bottom:0.3rem; display:block; }
        
        /* ── BUTTONS ── */
        .btn-primary {
            display:inline-flex; align-items:center; gap:0.5rem;
            padding:0.7rem 1.8rem; border-radius:10px;
            font-size:0.85rem; font-weight:600;
            background:linear-gradient(135deg,#7C3AED,#8B5CF6);
            color:#fff; border:none; cursor:pointer;
            transition:all 0.25s ease; width:100%;
            justify-content:center;
            box-shadow:0 4px 20px rgba(124,58,237,0.2);
        }
        .btn-primary:hover { transform:translateY(-2px); box-shadow:0 8px 30px rgba(124,58,237,0.3); }
        .btn-secondary {
            display:inline-flex; align-items:center; gap:0.5rem;
            padding:0.6rem 1.5rem; border-radius:10px;
            font-size:0.8rem; font-weight:500;
            background:rgba(124,58,237,0.08); color:#8B5CF6;
            border:1px solid rgba(124,58,237,0.12); cursor:pointer;
            transition:all 0.2s ease;
        }
        .btn-secondary:hover { background:rgba(124,58,237,0.15); border-color:rgba(124,58,237,0.2); }
        
        /* ── BADGES ── */
        .badge {
            font-size:0.65rem; font-weight:600; padding:0.2rem 0.7rem;
            border-radius:20px; display:inline-block;
            text-align:center; letter-spacing:0.3px;
        }
        .badge-urgent  { background:rgba(239,68,68,0.15);   color:#F87171; border:1px solid rgba(239,68,68,0.1);   }
        .badge-high    { background:rgba(251,146,60,0.12);   color:#FB923C; border:1px solid rgba(251,146,60,0.1);   }
        .badge-medium  { background:rgba(124,58,237,0.1);    color:#8B5CF6; border:1px solid rgba(124,58,237,0.08);  }
        .badge-low     { background:rgba(20,184,166,0.08);   color:#14B8A6; border:1px solid rgba(20,184,166,0.08);  }
        .badge-success { background:rgba(20,184,166,0.1);    color:#14B8A6; border:1px solid rgba(20,184,166,0.08);  }
        .badge-pending { background:rgba(251,191,36,0.1);    color:#FBBF24; border:1px solid rgba(251,191,36,0.08);  }
        .badge-error   { background:rgba(239,68,68,0.1);     color:#F87171; border:1px solid rgba(239,68,68,0.08);   }
        
        /* ── ACTIVITY ROWS ── */
        .activity-row {
            display:grid;
            grid-template-columns:1.4fr 1.2fr 1fr 0.9fr 0.9fr;
            padding:0.6rem 0;
            border-bottom:1px solid rgba(124,58,237,0.04);
            font-size:0.8rem; align-items:center; gap:0.5rem;
        }
        .activity-row.header {
            color:#64748B; font-weight:500; font-size:0.7rem;
            text-transform:uppercase; letter-spacing:0.5px;
            border-bottom:1px solid rgba(124,58,237,0.08);
            padding-bottom:0.6rem;
        }
        .activity-row .patient-name { color:#F8FAFC; font-weight:500; }

        /* ── RECORD ROWS ── */
        .record-row {
            display:flex; align-items:center; gap:0.9rem;
            padding:0.75rem 0.6rem; margin-bottom:0.4rem;
            border-radius:12px;
            background:rgba(255,255,255,0.02);
            border:1px solid rgba(255,255,255,0.04);
            transition:all 0.2s ease;
        }
        .record-row:hover {
            background:rgba(139,92,246,0.06);
            border-color:rgba(139,92,246,0.15);
            transform:translateX(2px);
        }
        .record-avatar {
            width:36px; height:36px; border-radius:10px; flex-shrink:0;
            display:flex; align-items:center; justify-content:center;
            background:linear-gradient(135deg, rgba(139,92,246,0.25), rgba(20,184,166,0.2));
            color:#C4B5FD; font-weight:700; font-size:0.85rem;
            border:1px solid rgba(139,92,246,0.2);
        }
        .record-main { flex:1; min-width:0; }
        .record-title { color:#F8FAFC; font-size:0.85rem; font-weight:600; }
        .record-sub { color:#94A3B8; font-size:0.72rem; margin-top:0.1rem; }
        .record-id { color:#64748B; font-size:0.68rem; font-family:monospace; }
        .record-right { text-align:right; flex-shrink:0; }
        
        /* ── RESULT CARDS ── */
        .result-card {
            background:rgba(22,28,52,0.6);
            border:1px solid rgba(124,58,237,0.08);
            border-radius:12px; padding:1.5rem; margin-top:1rem;
        }
        .result-card .result-item {
            display:flex; justify-content:space-between;
            padding:0.4rem 0;
            border-bottom:1px solid rgba(124,58,237,0.04);
            font-size:0.85rem;
        }
        .result-card .result-item .label { color:#94A3B8; }
        .result-card .result-item .value { color:#F8FAFC; font-weight:500; text-align:right; }
        
        /* ── DISCLAIMER ── */
        .disclaimer {
            font-size:0.65rem; color:#64748B;
            border-top:1px solid rgba(124,58,237,0.06);
            padding-top:0.8rem; margin-top:1rem;
            text-align:center; letter-spacing:0.3px;
        }
        
        /* ── RESPONSIVE ── */
        @media (max-width:768px) {
            .activity-row { grid-template-columns:1fr 1fr; font-size:0.7rem; gap:0.3rem; }
            .activity-row .hide-mobile { display:none; }
            .stat-card .stat-number { font-size:1.5rem; }
            .glass-card { padding:1rem; }
            .app-header .title { font-size:1.1rem; }
        }
        
        /* ── STREAMLIT OVERRIDES ── */
        .stTextInput>div>div>input,
        .stTextArea>div>div>textarea,
        .stSelectbox>div>div>select,
        .stNumberInput>div>div>input,
        .stDateInput>div>div>input,
        .stTimeInput>div>div>input {
            background:rgba(8,11,22,0.45) !important;
            border:1px solid rgba(139,92,246,0.14) !important;
            color:#F8FAFC !important; border-radius:10px !important;
            font-family:'Inter',sans-serif !important;
            transition:all 0.2s ease !important;
        }
        .stTextInput>div>div>input:focus,
        .stTextArea>div>div>textarea:focus,
        .stNumberInput>div>div>input:focus,
        .stDateInput>div>div>input:focus,
        .stTimeInput>div>div>input:focus {
            border-color:#8B5CF6 !important;
            box-shadow:0 0 0 3px rgba(139,92,246,0.12) !important;
        }
        .stSelectbox>div>div {
            background:rgba(8,11,22,0.45) !important;
            border:1px solid rgba(139,92,246,0.14) !important;
            border-radius:10px !important;
        }
        .stSelectbox>div>div:hover {
            border-color:rgba(139,92,246,0.3) !important;
        }
        label, .stTextInput label, .stTextArea label, .stSelectbox label,
        .stNumberInput label, .stDateInput label, .stTimeInput label {
            color:#94A3B8 !important; font-size:0.82rem !important; font-weight:500 !important;
        }

        div[data-testid="stForm"] {
            background:linear-gradient(160deg, rgba(28,34,60,0.55) 0%, rgba(16,20,38,0.35) 100%) !important;
            backdrop-filter:blur(22px) saturate(150%) !important;
            -webkit-backdrop-filter:blur(22px) saturate(150%) !important;
            border:1px solid rgba(139,92,246,0.14) !important;
            border-radius:18px !important;
            padding:1.6rem !important;
            box-shadow:0 10px 34px rgba(0,0,0,0.25), inset 0 1px 0 rgba(255,255,255,0.05) !important;
        }

        .stButton>button, .stFormSubmitButton>button {
            border-radius:10px !important;
            font-weight:600 !important;
            transition:all 0.25s ease !important;
        }
        div[data-testid="stForm"] .stFormSubmitButton>button {
            background:linear-gradient(135deg, #7C3AED, #8B5CF6) !important;
            color:#fff !important;
            border:none !important;
            box-shadow:0 4px 20px rgba(124,58,237,0.28) !important;
            width:100% !important;
        }
        div[data-testid="stForm"] .stFormSubmitButton>button:hover {
            transform:translateY(-2px) !important;
            box-shadow:0 8px 28px rgba(124,58,237,0.4) !important;
        }
        .main .stButton>button {
            background:rgba(139,92,246,0.08) !important;
            color:#C4B5FD !important;
            border:1px solid rgba(139,92,246,0.2) !important;
        }
        .main .stButton>button:hover {
            background:rgba(139,92,246,0.16) !important;
            border-color:rgba(139,92,246,0.35) !important;
            color:#F8FAFC !important;
        }

        section[data-testid="stSidebar"] {
            background:linear-gradient(180deg, #0D1020 0%, #0A0D1A 100%) !important;
            border-right:1px solid rgba(139,92,246,0.1) !important;
        }
        section[data-testid="stSidebar"] .stButton>button {
            display:flex !important; align-items:center !important; justify-content:flex-start !important;
            padding:0.7rem 1.1rem !important;
            border-radius:10px !important;
            font-size:0.85rem !important; font-weight:500 !important;
            transition:all 0.2s ease !important;
            width:100% !important;
        }
        section[data-testid="stSidebar"] .stButton>button[kind="secondary"] {
            background:rgba(255,255,255,0.02) !important;
            color:#94A3B8 !important;
            border:1px solid rgba(255,255,255,0.05) !important;
        }
        section[data-testid="stSidebar"] .stButton>button[kind="secondary"]:hover {
            background:rgba(139,92,246,0.08) !important;
            color:#F8FAFC !important;
            border-color:rgba(139,92,246,0.18) !important;
        }
        section[data-testid="stSidebar"] .stButton>button[kind="primary"] {
            background:linear-gradient(135deg, rgba(124,58,237,0.9), rgba(139,92,246,0.95)) !important;
            color:#fff !important;
            border:1px solid rgba(167,139,250,0.4) !important;
            box-shadow:0 4px 18px rgba(124,58,237,0.3), inset 0 1px 0 rgba(255,255,255,0.12) !important;
        }
        section[data-testid="stSidebar"] .stButton>button[kind="primary"]:hover {
            box-shadow:0 6px 22px rgba(124,58,237,0.4), inset 0 1px 0 rgba(255,255,255,0.15) !important;
        }

        div[data-testid="stAlert"] {
            border-radius:12px !important;
            backdrop-filter:blur(16px) !important;
            -webkit-backdrop-filter:blur(16px) !important;
            border:1px solid rgba(255,255,255,0.06) !important;
        }
        div[data-testid="stAlertContentSuccess"], div[data-testid="stAlert"]:has(div[data-testid="stAlertContentSuccess"]) {
            background:rgba(20,184,166,0.08) !important;
        }
        div[data-testid="stAlertContentError"], div[data-testid="stAlert"]:has(div[data-testid="stAlertContentError"]) {
            background:rgba(239,68,68,0.08) !important;
        }
        div[data-testid="stAlertContentInfo"], div[data-testid="stAlert"]:has(div[data-testid="stAlertContentInfo"]) {
            background:rgba(139,92,246,0.08) !important;
        }

        hr { border-color:rgba(124,58,237,0.06) !important; margin:1.5rem 0 !important; }
        ::-webkit-scrollbar       { width:4px; height:4px; }
        ::-webkit-scrollbar-track { background:#0D1020; }
        ::-webkit-scrollbar-thumb { background:#7C3AED; border-radius:10px; }
        
        .loading-spinner {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(124,58,237,0.1);
            border-radius: 50%;
            border-top-color: #7C3AED;
            animation: spin 1s ease-in-out infinite;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
    </style>
    """, unsafe_allow_html=True)

# ================================================
# N8N WEBHOOK FUNCTIONS
# ================================================

def send_to_n8n(feature_type, data):
    try:
        payload = {
            "feature_type": feature_type,
            "data": data,
            "timestamp": datetime.now().isoformat(),
            "source": "streamlit_dashboard"
        }
        
        response = requests.post(
            N8N_WEBHOOK_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        if response.status_code == 200:
            return {
                "success": True,
                "data": response.json() if response.text else {},
                "status_code": response.status_code
            }
        else:
            return {
                "success": False,
                "error": f"n8n returned status {response.status_code}",
                "status_code": response.status_code,
                "response_text": response.text
            }
    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "error": "Cannot connect to n8n. Please ensure n8n is running."
        }
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "error": "n8n request timed out. Please check if n8n is responding."
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Error: {str(e)}"
        }

# ================================================
# UI COMPONENTS
# ================================================

def render_header():
    now = datetime.now()
    date_str = now.strftime("%A, %B %d, %Y • %I:%M %p")
    col_left, col_right = st.columns([2, 1])
    with col_left:
        st.markdown("""
            <div class="app-header">
                <div class="title">🩺 CarePilot AI</div>
                <div class="subtitle">AI-Powered Healthcare Automation Platform</div>
            </div>
        """, unsafe_allow_html=True)
    with col_right:
        st.markdown(f"""
            <div class="app-header">
                <div class="header-right">
                    <div class="status-badge">
                        <span class="dot"></span>System Online
                    </div>
                    <div style="margin-top:0.3rem;font-size:0.7rem;color:#64748B;">{date_str}</div>
                </div>
            </div>
        """, unsafe_allow_html=True)

def render_sidebar():
    st.sidebar.markdown("""
        <div class="sidebar-brand">
            <h1>🩺 CarePilot</h1>
            <div class="subtitle">AI-Powered Healthcare Automation</div>
        </div>
    """, unsafe_allow_html=True)
    
    nav_items = [
        {"id":"dashboard",    "icon":"📊", "label":"Dashboard",          "badge":None},
        {"id":"intake",       "icon":"👤", "label":"Patient Intake",      "badge":None},
        {"id":"appointments", "icon":"📅", "label":"Appointments",        "badge":None},
        {"id":"symptom",      "icon":"🩺", "label":"Symptom Assessment",  "badge":None},
        {"id":"queries",      "icon":"💬", "label":"Patient Queries",     "badge":None},
        {"id":"followups",    "icon":"🔔", "label":"Follow-ups",          "badge":None},
    ]
    
    if 'current_page' not in st.session_state:
        st.session_state.current_page = 'dashboard'
    
    for item in nav_items:
        is_active = st.session_state.current_page == item['id']
        if st.sidebar.button(
            key=f"nav_{item['id']}",
            label=f"{item['icon']} {item['label']}",
            use_container_width=True,
            type="primary" if is_active else "secondary"
        ):
            st.session_state.current_page = item['id']
            st.rerun()
    
    st.sidebar.markdown("""
        <div class="sidebar-status">
            <div class="status-indicator">
                <span class="status-dot"></span>
                <span style="color:#94A3B8;">Automation Online</span>
                <span style="color:#64748B;font-size:0.6rem;margin-left:auto;">v2.2.0</span>
            </div>
        </div>
    """, unsafe_allow_html=True)

def render_badge(status_type, text):
    badge_class = {
        'urgent':'badge-urgent','high':'badge-high','medium':'badge-medium',
        'low':'badge-low','success':'badge-success','pending':'badge-pending',
        'error':'badge-error','completed':'badge-success','in progress':'badge-pending'
    }.get(status_type.lower(), 'badge-medium')
    return f'<span class="badge {badge_class}">{text}</span>'

# ================================================
# PAGES
# ================================================

def _initials(name: str) -> str:
    parts = str(name).strip().split()
    if not parts or parts[0] == "":
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()

def _flatten_html(html: str) -> str:
    return "\n".join(line.strip() for line in html.strip().splitlines())

def page_dashboard():
    col_a, col_b = st.columns([5, 1])
    with col_b:
        if st.button("🔄 Refresh", key="refresh_dashboard", use_container_width=True):
            st.rerun()

    stats, data_available = get_dashboard_stats()

    col1,col2,col3,col4 = st.columns(4)
    for col,(icon,num,label,trend,direction) in zip([col1,col2,col3,col4],stats):
        with col:
            st.markdown(f"""
                <div class="stat-card">
                    <div class="stat-icon">{icon}</div>
                    <div class="stat-number">{num}</div>
                    <div class="stat-label">{label}</div>
                    <div class="stat-trend {'down' if direction=='down' else ''}">{trend}</div>
                </div>
            """, unsafe_allow_html=True)

    if not data_available:
        st.info(
            "📡 Live data isn't loading yet. Make sure the CarePilot Google Sheet is shared as "
            "**\"Anyone with the link → Viewer\"**, and that the Patients/Appointments tabs have data."
        )

    st.markdown("<br>", unsafe_allow_html=True)

    col_left, col_right = st.columns(2)

    with col_left:
        patients = get_recent_patients(limit=6)
        rows_html = ""
        if patients:
            for p in patients:
                status_badge = render_badge(
                    'success' if str(p['status']).lower() in ('active','created') else 'pending',
                    p['status']
                )
                rows_html += f"""
                    <div class="record-row">
                        <div class="record-avatar">{_initials(p['name'])}</div>
                        <div class="record-main">
                            <div class="record-title">{p['name']}</div>
                            <div class="record-sub">{p['age']} yrs · {p['gender']} · <span class="record-id">{p['id']}</span></div>
                        </div>
                        <div class="record-right">{status_badge}</div>
                    </div>
                """
        else:
            rows_html = """
                <div style="text-align:center;padding:1.5rem;color:#64748B;font-size:0.8rem;">
                    No patient records yet — register one via Patient Intake.
                </div>
            """
        st.markdown(_flatten_html(f"""
            <div class="glass-card">
                <div class="card-header">
                    <div class="card-title">👤 Recent Patients</div>
                    <span class="card-badge">Live</span>
                </div>
                {rows_html}
            </div>
        """), unsafe_allow_html=True)

    with col_right:
        appts = get_recent_appointments(limit=6)
        rows_html = ""
        if appts:
            for a in appts:
                priority_badge = render_badge(a['priority'].lower(), a['priority'])
                rows_html += f"""
                    <div class="record-row">
                        <div class="record-avatar">{_initials(a['patient'])}</div>
                        <div class="record-main">
                            <div class="record-title">{a['patient']}</div>
                            <div class="record-sub">{a['department']} · {a['date']} · <span class="record-id">{a['id']}</span></div>
                        </div>
                        <div class="record-right">{priority_badge}</div>
                    </div>
                """
        else:
            rows_html = """
                <div style="text-align:center;padding:1.5rem;color:#64748B;font-size:0.8rem;">
                    No appointments yet — request one via Appointments.
                </div>
            """
        st.markdown(_flatten_html(f"""
            <div class="glass-card">
                <div class="card-header">
                    <div class="card-title">📅 Recent Appointments</div>
                    <span class="card-badge">Live</span>
                </div>
                {rows_html}
            </div>
        """), unsafe_allow_html=True)

    st.markdown('<div class="disclaimer">⚕️ CarePilot AI provides informational support and workflow routing, not medical diagnosis or treatment.</div>', unsafe_allow_html=True)

def page_patient_intake():
    st.markdown("""
        <div style="margin-bottom:1.5rem;">
            <h2 style="color:#F8FAFC;font-weight:700;font-size:1.3rem;">👤 Patient Intake</h2>
            <p style="color:#94A3B8;font-size:0.9rem;">AI-powered patient registration and record creation via n8n</p>
        </div>
    """, unsafe_allow_html=True)
    col_form, col_result = st.columns([1,1])
    with col_form:
        with st.form(key="patient_intake_form"):
            full_name = st.text_input("Full Name *", placeholder="Enter patient's full name")
            age       = st.number_input("Age *", min_value=0, max_value=150, step=1, value=30)
            gender    = st.selectbox("Gender *", ["Select Gender","Male","Female","Other"])
            contact   = st.text_input("Contact Number *", placeholder="+92 300 1234567")
            email     = st.text_input("Email", placeholder="patient@example.com")
            medical_history = st.text_area("Medical History / Notes", placeholder="Any relevant medical history...", height=100)
            submitted = st.form_submit_button("Register Patient")
            if submitted:
                if not full_name or not contact or gender == "Select Gender":
                    st.error("Please fill in all required fields (*)")
                else:
                    with st.spinner("Processing patient registration via n8n..."):
                        next_id = get_next_patient_id()
                        n8n_response = send_to_n8n("intake", {
                            "full_name": full_name,
                            "age": age,
                            "gender": gender,
                            "contact": contact,
                            "email": email,
                            "medical_history": medical_history,
                            "suggested_patient_id": next_id
                        })
                        
                        if n8n_response["success"]:
                            response_data = n8n_response.get("data", {})
                            st.session_state.intake_submitted = True
                            st.session_state.intake_result = {
                                'patient_id': response_data.get("patient_id", next_id),
                                'name': full_name,
                                'age': age,
                                'gender': gender,
                                'contact': contact,
                                'email': email or "Not provided",
                                'health_notes': medical_history or "None",
                                'status': "Created",
                                'message': "Patient record created successfully via n8n",
                                'n8n_response': response_data
                            }
                            st.success("Patient registered successfully via n8n!")
                        else:
                            st.error(f"❌ n8n Error: {n8n_response.get('error', 'Unknown error')}")
                            st.info("Please check if n8n workflow is running and webhook URL is correct.")
    with col_result:
        if st.session_state.get('intake_submitted'):
            r = st.session_state.intake_result
            st.markdown(f"""
                <div class="result-card">
                    <h4 style="color:#14B8A6;font-size:0.9rem;margin-bottom:1rem;">✅ Registration Result</h4>
                    <div class="result-item"><span class="label">Patient ID</span><span class="value" style="color:#8B5CF6;">{r.get('patient_id', 'Processing...')}</span></div>
                    <div class="result-item"><span class="label">Name</span><span class="value">{r['name']}</span></div>
                    <div class="result-item"><span class="label">Age</span><span class="value">{r['age']}</span></div>
                    <div class="result-item"><span class="label">Gender</span><span class="value">{r['gender']}</span></div>
                    <div class="result-item"><span class="label">Contact</span><span class="value">{r['contact']}</span></div>
                    <div class="result-item"><span class="label">Status</span><span class="value" style="color:#14B8A6;">{r['status']}</span></div>
                    <div style="margin-top:0.8rem;padding-top:0.8rem;border-top:1px solid rgba(124,58,237,0.06);">
                        <span style="color:#94A3B8;font-size:0.8rem;">{r['message']}</span>
                    </div>
                    <div style="margin-top:0.5rem;padding:0.5rem;background:rgba(124,58,237,0.05);border-radius:8px;">
                        <span style="color:#64748B;font-size:0.7rem;">📋 Health Notes: {r['health_notes']}</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
                <div class="result-card" style="text-align:center;padding:2rem;">
                    <div style="font-size:2rem;margin-bottom:0.5rem;">📋</div>
                    <div style="color:#94A3B8;font-size:0.9rem;">Patient registration result will appear here</div>
                    <div style="color:#64748B;font-size:0.8rem;margin-top:0.3rem;">Data will be processed by n8n workflow</div>
                </div>
            """, unsafe_allow_html=True)
    st.markdown('<div class="disclaimer">⚕️ Patient data is processed securely via n8n workflow.</div>', unsafe_allow_html=True)

def page_appointments():
    st.markdown("""
        <div style="margin-bottom:1.5rem;">
            <h2 style="color:#F8FAFC;font-weight:700;font-size:1.3rem;">📅 Appointment Management</h2>
            <p style="color:#94A3B8;font-size:0.9rem;">Intelligent appointment scheduling via n8n</p>
        </div>
    """, unsafe_allow_html=True)
    col_form, col_result = st.columns([1,1])
    with col_form:
        with st.form(key="appointment_form"):
            patient_id   = st.text_input("Patient ID", placeholder="CP-2026-0042")
            patient_name = st.text_input("Patient Name *", placeholder="Enter patient's full name")
            preferred_date = st.date_input("Preferred Date *", min_value=datetime.now().date())
            preferred_time = st.time_input("Preferred Time *", value=datetime.now().time())
            reason = st.text_area("Reason / Symptoms *", placeholder="Describe the reason for appointment...", height=100)
            submitted = st.form_submit_button("Request Appointment")
            if submitted:
                if not patient_name or not reason:
                    st.error("Please fill in all required fields (*)")
                else:
                    with st.spinner("Processing appointment via n8n..."):
                        next_appt_id = get_next_appt_id()
                        n8n_response = send_to_n8n("appointment", {
                            "patient_id": patient_id,
                            "patient_name": patient_name,
                            "preferred_date": preferred_date.strftime("%Y-%m-%d"),
                            "preferred_time": preferred_time.strftime("%H:%M"),
                            "reason": reason,
                            "suggested_appt_id": next_appt_id
                        })
                        
                        if n8n_response["success"]:
                            response_data = n8n_response.get("data", {})
                            st.session_state.appointment_submitted = True
                            st.session_state.appointment_result = {
                                'appointment_id': response_data.get("appointment_id", next_appt_id),
                                'patient_name': patient_name,
                                'patient_id': patient_id or "Not provided",
                                'date': preferred_date.strftime("%B %d, %Y"),
                                'time': preferred_time.strftime("%I:%M %p"),
                                'department': response_data.get("department", "Processing..."),
                                'priority': response_data.get("priority", "Processing..."),
                                'urgency': response_data.get("urgency_level", "Processing..."),
                                'status': "Pending",
                                'notes': reason,
                                'recommended_action': response_data.get("recommended_action", "Processing..."),
                                'n8n_response': response_data
                            }
                            st.success("Appointment request submitted successfully via n8n!")
                        else:
                            st.error(f"❌ n8n Error: {n8n_response.get('error', 'Unknown error')}")
                            st.info("Please check if n8n workflow is running and webhook URL is correct.")
    with col_result:
        if st.session_state.get('appointment_submitted'):
            r = st.session_state.appointment_result
            pb = render_badge(r['priority'].lower(), r['priority']) if r['priority'] != "Processing..." else "Processing..."
            sb = render_badge('pending', r['status'])
            st.markdown(f"""
                <div class="result-card">
                    <h4 style="color:#8B5CF6;font-size:0.9rem;margin-bottom:1rem;">📌 Appointment Request</h4>
                    <div class="result-item"><span class="label">Appointment ID</span><span class="value" style="color:#8B5CF6;">{r['appointment_id']}</span></div>
                    <div class="result-item"><span class="label">Patient</span><span class="value">{r['patient_name']}</span></div>
                    <div class="result-item"><span class="label">Department</span><span class="value">{r['department']}</span></div>
                    <div class="result-item"><span class="label">Date & Time</span><span class="value">{r['date']} at {r['time']}</span></div>
                    <div class="result-item"><span class="label">Priority</span><span class="value">{pb}</span></div>
                    <div class="result-item"><span class="label">Urgency</span><span class="value" style="color:#FB923C;">{r['urgency']}</span></div>
                    <div class="result-item"><span class="label">Status</span><span class="value">{sb}</span></div>
                    <div style="margin-top:0.8rem;padding-top:0.8rem;border-top:1px solid rgba(124,58,237,0.06);">
                        <span style="color:#94A3B8;font-size:0.8rem;">💡 {r['recommended_action']}</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
                <div class="result-card" style="text-align:center;padding:2rem;">
                    <div style="font-size:2rem;margin-bottom:0.5rem;">📅</div>
                    <div style="color:#94A3B8;font-size:0.9rem;">Appointment request result will appear here</div>
                    <div style="color:#64748B;font-size:0.8rem;margin-top:0.3rem;">n8n will classify department and determine priority</div>
                </div>
            """, unsafe_allow_html=True)
    st.markdown('<div class="disclaimer">⚕️ Appointment priority routing is handled by n8n workflow.</div>', unsafe_allow_html=True)

def page_symptom_assessment():
    st.markdown("""
        <div style="margin-bottom:1.5rem;">
            <h2 style="color:#F8FAFC;font-weight:700;font-size:1.3rem;">🩺 Symptom Assessment</h2>
            <p style="color:#94A3B8;font-size:0.9rem;">AI-assisted symptom analysis via n8n</p>
        </div>
    """, unsafe_allow_html=True)
    col_input, col_result = st.columns([1,1])
    with col_input:
        with st.form(key="symptom_form"):
            patient_id = st.text_input("Patient ID (optional)", placeholder="CP-2026-0042")
            symptoms   = st.text_area("What symptoms or health concerns are you experiencing? *",
                                      placeholder="e.g., I've been having persistent headaches and dizziness...", height=120)
            submitted  = st.form_submit_button("Analyze Symptoms")
            if submitted:
                if not symptoms:
                    st.error("Please describe your symptoms")
                else:
                    with st.spinner("Analyzing symptoms via n8n AI..."):
                        n8n_response = send_to_n8n("symptom", {
                            "patient_id": patient_id,
                            "symptoms": symptoms
                        })
                        
                        if n8n_response["success"]:
                            response_data = n8n_response.get("data", {})
                            st.session_state.symptom_submitted = True
                            st.session_state.symptom_result = {
                                'query_id': response_data.get("query_id", "Processing..."),
                                'patient_id': patient_id or "Anonymous",
                                'summary': response_data.get("symptom_summary", "Processing..."),
                                'department': response_data.get("recommended_department", "Processing..."),
                                'urgency': response_data.get("urgency_level", "Processing..."),
                                'questions': response_data.get("suggested_questions", ["Processing..."]),
                                'disclaimer': "This is an informational assessment, not a medical diagnosis.",
                                'n8n_response': response_data
                            }
                            st.success("Symptom analysis completed via n8n AI!")
                        else:
                            st.error(f"❌ n8n Error: {n8n_response.get('error', 'Unknown error')}")
                            st.info("Please check if n8n workflow is running and webhook URL is correct.")
    with col_result:
        if st.session_state.get('symptom_submitted'):
            r  = st.session_state.symptom_result
            ub = render_badge(r['urgency'].lower(), r['urgency']) if r['urgency'] != "Processing..." else "Processing..."
            qs = ''.join([f'<li>{q}</li>' for q in r['questions'][:3]])
            st.markdown(f"""
                <div class="result-card">
                    <h4 style="color:#14B8A6;font-size:0.9rem;margin-bottom:1rem;">🔍 Assessment Result</h4>
                    <div class="result-item"><span class="label">Query ID</span><span class="value" style="color:#8B5CF6;">{r['query_id']}</span></div>
                    <div class="result-item"><span class="label">Patient ID</span><span class="value">{r['patient_id']}</span></div>
                    <div class="result-item"><span class="label">Symptom Summary</span><span class="value" style="font-size:0.8rem;text-align:right;">{r['summary']}</span></div>
                    <div class="result-item"><span class="label">Recommended Department</span><span class="value" style="color:#8B5CF6;">{r['department']}</span></div>
                    <div class="result-item"><span class="label">Urgency Level</span><span class="value">{ub}</span></div>
                    <div style="margin-top:0.8rem;padding-top:0.8rem;border-top:1px solid rgba(124,58,237,0.06);">
                        <div style="color:#94A3B8;font-size:0.8rem;margin-bottom:0.3rem;">📋 Suggested Questions:</div>
                        <ul style="color:#94A3B8;font-size:0.75rem;padding-left:1rem;margin:0;">{qs}</ul>
                    </div>
                    <div style="margin-top:0.8rem;padding:0.6rem;background:rgba(239,68,68,0.05);border-radius:8px;border:1px solid rgba(239,68,68,0.1);">
                        <span style="color:#F87171;font-size:0.7rem;">⚠️ {r['disclaimer']}</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
                <div class="result-card" style="text-align:center;padding:2rem;">
                    <div style="font-size:2rem;margin-bottom:0.5rem;">🩺</div>
                    <div style="color:#94A3B8;font-size:0.9rem;">Symptom analysis result will appear here</div>
                    <div style="color:#64748B;font-size:0.8rem;margin-top:0.3rem;">n8n will process symptoms and suggest department</div>
                </div>
            """, unsafe_allow_html=True)

def page_queries():
    st.markdown("""
        <div style="margin-bottom:1.5rem;">
            <h2 style="color:#F8FAFC;font-weight:700;font-size:1.3rem;">💬 Patient Query Router</h2>
            <p style="color:#94A3B8;font-size:0.9rem;">AI-powered intent detection via n8n</p>
        </div>
    """, unsafe_allow_html=True)
    col_input, col_result = st.columns([1,1])
    with col_input:
        with st.form(key="query_form"):
            patient_id = st.text_input("Patient ID (optional)", placeholder="CP-2026-0042")
            query      = st.text_area("Type your question or request... *",
                                      placeholder="e.g., I want to reschedule my appointment for next week...", height=100)
            submitted  = st.form_submit_button("Process Query")
            if submitted:
                if not query:
                    st.error("Please enter your question or request")
                else:
                    with st.spinner("Processing query via n8n AI..."):
                        n8n_response = send_to_n8n("query", {
                            "patient_id": patient_id,
                            "query": query
                        })
                        
                        if n8n_response["success"]:
                            response_data = n8n_response.get("data", {})
                            st.session_state.query_submitted = True
                            st.session_state.query_result = {
                                'message_id': response_data.get("message_id", "Processing..."),
                                'patient_id': patient_id or "Anonymous",
                                'raw_query': query,
                                'intent': response_data.get("intent", "Processing..."),
                                'confidence': response_data.get("confidence", "0.0"),
                                'workflow': response_data.get("workflow_triggered", "Processing..."),
                                'action': response_data.get("action", "Processing..."),
                                'status': "Completed",
                                'n8n_response': response_data
                            }
                            st.success("Query processed successfully via n8n AI!")
                        else:
                            st.error(f"❌ n8n Error: {n8n_response.get('error', 'Unknown error')}")
                            st.info("Please check if n8n workflow is running and webhook URL is correct.")
    with col_result:
        if st.session_state.get('query_submitted'):
            r  = st.session_state.query_result
            sb = render_badge('success', r['status'])
            st.markdown(f"""
                <div class="result-card">
                    <h4 style="color:#8B5CF6;font-size:0.9rem;margin-bottom:1rem;">🎯 Intent Detected</h4>
                    <div class="result-item"><span class="label">Message ID</span><span class="value" style="color:#8B5CF6;">{r['message_id']}</span></div>
                    <div class="result-item"><span class="label">Patient ID</span><span class="value">{r['patient_id']}</span></div>
                    <div class="result-item"><span class="label">Intent</span><span class="value" style="color:#8B5CF6;">{r['intent']}</span></div>
                    <div class="result-item"><span class="label">Confidence</span><span class="value">{int(float(r['confidence'])*100) if r['confidence'] != "0.0" else "--"}%</span></div>
                    <div class="result-item"><span class="label">Workflow Triggered</span><span class="value">{r['workflow']}</span></div>
                    <div class="result-item"><span class="label">Action Taken</span><span class="value" style="color:#14B8A6;">{r['action']}</span></div>
                    <div class="result-item"><span class="label">Status</span><span class="value">{sb}</span></div>
                </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
                <div class="result-card" style="text-align:center;padding:2rem;">
                    <div style="font-size:2rem;margin-bottom:0.5rem;">💬</div>
                    <div style="color:#94A3B8;font-size:0.9rem;">AI intent detection result will appear here</div>
                    <div style="color:#64748B;font-size:0.8rem;margin-top:0.3rem;">n8n will detect intent and trigger appropriate workflow</div>
                </div>
            """, unsafe_allow_html=True)

def page_followups():
    st.markdown("""
        <div style="margin-bottom:1.5rem;">
            <h2 style="color:#F8FAFC;font-weight:700;font-size:1.3rem;">🔔 Follow-ups & Alerts</h2>
            <p style="color:#94A3B8;font-size:0.9rem;">Automated reminders via n8n</p>
        </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("📧 Send Reminders", key="send_reminders", use_container_width=True):
            with st.spinner("Sending reminders via n8n..."):
                try:
                    payload = {
                        "action": "send_reminders",
                        "timestamp": datetime.now().isoformat()
                    }
                    response = requests.post(
                        N8N_FOLLOWUP_URL,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                        timeout=30
                    )
                    if response.status_code == 200:
                        st.success("✅ Reminders sent successfully via n8n!")
                    else:
                        st.error(f"❌ n8n Error: Status {response.status_code}")
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")

    with col2:
        if st.button("🔔 Send Staff Alerts", key="send_staff_alerts", use_container_width=True):
            with st.spinner("Sending staff alerts via n8n..."):
                try:
                    payload = {
                        "action": "send_staff_alerts",
                        "timestamp": datetime.now().isoformat()
                    }
                    response = requests.post(
                        N8N_FOLLOWUP_URL,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                        timeout=30
                    )
                    if response.status_code == 200:
                        st.success("✅ Staff alerts sent successfully via n8n!")
                    else:
                        st.error(f"❌ n8n Error: Status {response.status_code}")
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")

    st.markdown("""
        <div style="background:rgba(20,184,166,0.05);border:1px solid rgba(20,184,166,0.08);
                    border-radius:10px;padding:1rem;margin-top:1rem;">
            <div style="display:flex;align-items:center;gap:0.8rem;">
                <span style="font-size:1.2rem;">🔄</span>
                <div>
                    <div style="color:#F8FAFC;font-size:0.85rem;font-weight:500;">Automated Schedule</div>
                    <div style="color:#94A3B8;font-size:0.75rem;">Daily at 9:00 AM — reminders & alerts triggered automatically via n8n</div>
                </div>
            </div>
        </div>
    """, unsafe_allow_html=True)

# ================================================
# MAIN
# ================================================
def main():
    load_css()
    render_sidebar()
    render_header()
    page = st.session_state.get('current_page','dashboard')
    pages = {
        'dashboard':    page_dashboard,
        'intake':       page_patient_intake,
        'appointments': page_appointments,
        'symptom':      page_symptom_assessment,
        'queries':      page_queries,
        'followups':    page_followups,
    }
    pages.get(page, page_dashboard)()

if __name__ == "__main__":
    main()
