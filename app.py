import streamlit as st
import pandas as pd
import time
import plotly.graph_objects as go
from pymongo import MongoClient
import certifi

# 1. Page Config
st.set_page_config(page_title="MT5 Cloud Terminal", page_icon="🌐", layout="wide")

# 2. Database Connection
@st.cache_resource
def get_database():
    try:
        uri = st.secrets["MONGO_URI"]
        client = MongoClient(uri, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        return client['TradingSaaS']
    except Exception as e:
        st.error(f"Database Offline: {e}")
        return None

db = get_database()

# 3. Session Management
if "logged_in_user" not in st.session_state:
    st.session_state.logged_in_user = None

# 4. Sidebar Login & Controls
st.sidebar.header("🔐 MT5 Access Control")

# Login Section
if not st.session_state.logged_in_user:
    login_id = st.sidebar.text_input("MT5 Account Number", placeholder="e.g. 5123456")
    login_pass = st.sidebar.text_input("MT5 Password", type="password")
    login_server = st.sidebar.text_input("Broker Server", value="MetaQuotes-Demo")
    
    if st.sidebar.button("Connect Account"):
        if login_id and login_pass:
            # Save/Update credentials in MongoDB
            db['UserStates'].update_one(
                {"user_id": login_id},
                {"$set": {
                    "mt5_login": login_id,
                    "mt5_pass": login_pass,
                    "mt5_server": login_server,
                    "request_sync": True # Tells the bot to start this account
                }},
                upsert=True
            )
            st.session_state.logged_in_user = login_id
            st.rerun()
else:
    st.sidebar.success(f"Connected: {st.session_state.logged_in_user}")
    if st.sidebar.button("Logout"):
        st.session_state.logged_in_user = None
        st.rerun()

# 5. Load Data for Logged-in User
user_data = None
if st.session_state.logged_in_user:
    user_data = db['UserStates'].find_one({"user_id": st.session_state.logged_in_user})

# 6. Main Dashboard UI
st.title("📊 Universal MT5 Multi-Monitor")

# Show Placeholders if not logged in
balance = user_data.get('balance', 0.00) if user_data else 0.00
equity = user_data.get('equity', 0.00) if user_data else 0.00
profit = user_data.get('profit', 0.00) if user_data else 0.00

# --- METRICS ROW ---
col1, col2, col3, col4 = st.columns(4)
col1.metric("Account Balance", f"${balance:,.2f}")
col2.metric("Current Equity", f"${equity:,.2f}", f"{profit:,.2f}")
col3.metric("Status", "ONLINE" if user_data else "OFFLINE")
col4.metric("User ID", st.session_state.logged_in_user if st.session_state.logged_in_user else "None")

# --- GAUGE ---
st.subheader("Account Health")
fig = go.Figure(go.Indicator(
    mode = "gauge+number",
    value = equity,
    gauge = {
        'axis': {'range': [None, balance * 1.5 if balance > 0 else 1000]},
        'bar': {'color': "#00ffcc"},
        'steps': [{'range': [0, balance], 'color': "#2a2a2a"}],
        'threshold': {'line': {'color': "white", 'width': 4}, 'value': balance}
    }
))
fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"}, height=350)
st.plotly_chart(fig, use_container_width=True)

# 7. Sidebar Settings (Only visible if logged in)
if st.session_state.logged_in_user and user_data:
    st.sidebar.divider()
    st.sidebar.header("⚙️ Strategy Settings")
    
    catalog = user_data.get("mt5_catalog", ["EURUSD", "GBPUSD"])
    selected = st.sidebar.multiselect("Trade Symbols", options=catalog, default=user_data.get("active_symbols", []))
    risk = st.sidebar.slider("Risk Level (%)", 0.1, 5.0, 1.0)
    
    if st.sidebar.button("Save Strategy"):
        db['UserStates'].update_one(
            {"user_id": st.session_state.logged_in_user},
            {"$set": {"active_symbols": selected, "risk_value": risk}}
        )
        st.sidebar.success("Settings Syncing...")

# Auto-refresh if logged in
if st.session_state.logged_in_user:
    time.sleep(5)
    st.rerun()