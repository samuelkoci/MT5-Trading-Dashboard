import streamlit as st
import pandas as pd
import time
import plotly.graph_objects as go
from pymongo import MongoClient
import certifi
from cryptography.fernet import Fernet

# 1. Page Config
st.set_page_config(page_title="MT5 Cloud Terminal", page_icon="🌐", layout="wide")

# --- MASTER SYMBOL WHITELIST ---
# Your curated list of professional assets
GLOBAL_WHITELIST = [
    "UKOUSD", "USOUSD", "XAGUSD", "XAUUSD", "XPTUSD", 
    "AUDCAD", "AUDCHF", "AUDJPY", "AUDUSD", "EURAUD", 
    "EURCAD", "EURCHF", "EURGBP", "EURJPY", "EURUSD", 
    "GBPUSD", "USDCAD", "USDCHF", "USDJPY", "GER30", 
    "EUSTX50", "FRA40", "HK50", "SPX500", "UK100", 
    "BTCUSD", "ETHUSD"
]

# --- BROKER SERVER DATA ---
COMMON_SERVERS = [
    "MetaQuotes-Demo", "FundedNext-Server", "FundedNext-Server2", "FundedNext-Server3", 
    "ICMarkets-Demo", "ICMarkets-Live", "Pepperstone-MT5-Live", "Exness-MT5-Real", 
    "XMGlobal-MT5", "FTMO-Server", "Custom (Type below)"
]

# 2. Database Connection Function
@st.cache_resource
def get_database():
    try:
        if "MONGO_URI" not in st.secrets:
            st.error("❌ 'MONGO_URI' not found in Streamlit Secrets!")
            return None
        uri = st.secrets["MONGO_URI"].strip() 
        client = MongoClient(uri, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        return client['TradingSaaS']
    except Exception as e:
        st.error(f"🔌 Connection Error: {e}")
        return None

db = get_database()

# Initialize the Cipher Suite
cipher_suite = None
try:
    if "ENCRYPTION_KEY" in st.secrets:
        cipher_suite = Fernet(st.secrets["ENCRYPTION_KEY"])
    else:
        st.error("🔐 Encryption Key missing in Streamlit Secrets.")
except Exception as e:
    st.error(f"🔐 Invalid Encryption Key: {e}")

if db is None:
    st.warning("Please check your MongoDB URI and Network Access (IP Whitelist).")
    st.stop()

# 3. Session Management
if "logged_in_user" not in st.session_state:
    st.session_state.logged_in_user = None

# 4. Sidebar Login & Controls
st.sidebar.header("🔐 MT5 Access Control")

if not st.session_state.logged_in_user:
    with st.sidebar.form("login_panel"):
        login_id = st.text_input("MT5 Account Number", placeholder="e.g. 5123456")
        login_pass = st.text_input("MT5 Password", type="password")
        selected_server = st.selectbox("Search Broker Server", options=COMMON_SERVERS)
        custom_server = st.text_input("If 'Custom', type server name here:", placeholder="e.g. NextFunded-Server")
        
        submit_button = st.form_submit_button("Connect Account")
        
        if submit_button:
            if login_id and login_pass and cipher_suite:
                password_bytes = login_pass.encode()
                encrypted_pw = cipher_suite.encrypt(password_bytes).decode()
                final_server = custom_server if selected_server == "Custom (Type below)" else selected_server
                
                db['UserStates'].update_one(
                    {"user_id": login_id},
                    {"$set": {
                        "mt5_login": login_id,
                        "mt5_pass": encrypted_pw,
                        "mt5_server": final_server,
                        "request_sync": True 
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

# 5. Load Data
user_data = None
if st.session_state.logged_in_user:
    user_data = db['UserStates'].find_one({"user_id": st.session_state.logged_in_user})

# 6. Main Dashboard UI
st.title("📊 Universal MT5 Multi-Monitor")

if user_data:
    balance = user_data.get('balance', 0.00)
    equity = user_data.get('equity', 0.00)
    profit = user_data.get('profit', 0.00)
    status = user_data.get('connection_status', 'ONLINE')
else:
    balance, equity, profit, status = 0.00, 0.00, 0.00, "OFFLINE"

col1, col2, col3, col4 = st.columns(4)
col1.metric("Account Balance", f"${balance:,.2f}")
col2.metric("Current Equity", f"${equity:,.2f}", f"{profit:,.2f}")
col3.metric("Status", status)
col4.metric("User ID", st.session_state.logged_in_user if st.session_state.logged_in_user else "N/A")

# --- GAUGE ---
st.subheader("Account Health")
fig = go.Figure(go.Indicator(
    mode = "gauge+number",
    value = equity,
    gauge = {
        'axis': {'range': [None, balance * 1.2 if balance > 0 else 1000]},
        'bar': {'color': "#00ffcc"},
        'steps': [{'range': [0, balance], 'color': "#2a2a2a"}],
        'threshold': {'line': {'color': "white", 'width': 4}, 'value': balance}
    }
))
fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"}, height=350)
st.plotly_chart(fig, use_container_width=True)

# --- 7. STRATEGY SETTINGS (SMART FILTERING) ---
if st.session_state.logged_in_user and user_data:
    st.sidebar.divider()
    st.sidebar.header("⚙️ Strategy Settings")
    
    # Logic: Cross-reference Whitelist with User's Broker Catalog
    broker_catalog = user_data.get("mt5_catalog", [])
    
    if not broker_catalog:
        st.sidebar.warning("⏳ Syncing Broker Catalog...")
        display_options = ["EURUSD", "GBPUSD", "XAUUSD"] # Default safe fallback
    else:
        # Filter: Only show symbols present in BOTH our Whitelist and the Broker's catalog
        display_options = [s for s in GLOBAL_WHITELIST if s in broker_catalog]
        unsupported = [s for s in GLOBAL_WHITELIST if s not in broker_catalog]

    active_symbols = user_data.get("active_symbols", [])
    
    selected = st.sidebar.multiselect(
        "Trade Symbols", 
        options=display_options, 
        default=[s for s in active_symbols if s in display_options],
        help="Only symbols supported by your current broker server are shown."
    )
    
    # Show Greyed-out/Blocked Symbols in an expander for transparency
    if broker_catalog and unsupported:
        with st.sidebar.expander("🚫 Unsupported by your Broker"):
            st.caption("The following curated symbols are not available on your specific server:")
            st.write(", ".join(unsupported))

    saved_risk = float(user_data.get("risk_value", 1.0))
    risk = st.sidebar.slider("Risk Level (%)", 0.1, 10.0, saved_risk)
    
    if st.sidebar.button("Save & Sync Strategy"):
        db['UserStates'].update_one(
            {"user_id": st.session_state.logged_in_user},
            {"$set": {
                "active_symbols": selected, 
                "risk_value": risk,
                "request_sync": True
            }}
        )
        st.sidebar.success("Settings Synced! 📡")

# --- AUTO REFRESH ---
if st.session_state.logged_in_user:
    time.sleep(5)
    st.rerun()