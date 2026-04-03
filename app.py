import streamlit as st
import pandas as pd
import time
import plotly.graph_objects as go
from pymongo import MongoClient
import certifi

# 1. Page Config
st.set_page_config(page_title="MT5 Cloud Terminal", page_icon="🌐", layout="wide")

# --- BROKER SERVER DATA ---
# This acts as your "Searchable" database for the user
COMMON_SERVERS = [
    "MetaQuotes-Demo", "ICMarkets-Demo", "ICMarkets-Live", "Pepperstone-MT5-Live",
    "Exness-MT5-Real", "XMGlobal-MT5", "FBS-Real", "FTMO-Server", "Tickmill-Live",
    "Vantage-Live", "Hantec-Live", "Custom (Type below)"
]

# 2. Database Connection
@st.cache_resource
def get_database():
    try:
        # Pull from Secrets
        uri = st.secrets["MONGO_URI"]
        client = MongoClient(uri, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        return client['TradingSaaS']
    except Exception as e:
        st.error(f"🔌 Database Offline: {e}")
        return None

db = get_database()

# 3. Session Management
if "logged_in_user" not in st.session_state:
    st.session_state.logged_in_user = None

# 4. Sidebar Login & Controls
st.sidebar.header("🔐 MT5 Access Control")

if not st.session_state.logged_in_user:
    # Use a Form to prevent the app from refreshing every time you type a letter
    with st.sidebar.form("login_panel"):
        login_id = st.text_input("MT5 Account Number", placeholder="e.g. 5123456")
        login_pass = st.text_input("MT5 Password", type="password")
        
        # SEARCH BAR: Using selectbox with search enabled by default in Streamlit
        selected_server = st.selectbox("Search Broker Server", options=COMMON_SERVERS)
        
        # Logic for Custom Server
        custom_server = st.text_input("If 'Custom', type server name here:", placeholder="e.g. MyBroker-Live-01")
        
        submit_button = st.form_submit_button("Connect Account")
        
        if submit_button:
            if login_id and login_pass:
                # Determine which server name to use
                final_server = custom_server if selected_server == "Custom (Type below)" else selected_server
                
                if db is not None:
                    db['UserStates'].update_one(
                        {"user_id": login_id},
                        {"$set": {
                            "mt5_login": login_id,
                            "mt5_pass": login_pass,
                            "mt5_server": final_server,
                            "request_sync": True 
                        }},
                        upsert=True
                    )
                    st.session_state.logged_in_user = login_id
                    st.rerun()
                else:
                    st.error("Database connection failed. Please check your MONGO_URI.")
            else:
                st.warning("Please enter both ID and Password.")
else:
    st.sidebar.success(f"Connected: {st.session_state.logged_in_user}")
    if st.sidebar.button("Logout"):
        st.session_state.logged_in_user = None
        st.rerun()

# 5. Load Data
user_data = None
if st.session_state.logged_in_user and db is not None:
    user_data = db['UserStates'].find_one({"user_id": st.session_state.logged_in_user})

# 6. Main Dashboard UI
st.title("📊 Universal MT5 Multi-Monitor")

# Values (Defaults to 0.00 if not logged in)
balance = user_data.get('balance', 0.00) if user_data else 0.00
equity = user_data.get('equity', 0.00) if user_data else 0.00
profit = user_data.get('profit', 0.00) if user_data else 0.00

col1, col2, col3, col4 = st.columns(4)
col1.metric("Account Balance", f"${balance:,.2f}")
col2.metric("Current Equity", f"${equity:,.2f}", f"{profit:,.2f}")
col3.metric("Status", "ONLINE" if user_data else "OFFLINE")
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

# 7. Sidebar Strategy Settings
if st.session_state.logged_in_user and user_data:
    st.sidebar.divider()
    st.sidebar.header("⚙️ Strategy Settings")
    
    catalog = user_data.get("mt5_catalog", ["EURUSD", "GBPUSD"])
    active = user_data.get("active_symbols", [])
    
    selected = st.sidebar.multiselect("Trade Symbols", options=catalog, default=active)
    risk = st.sidebar.slider("Risk Level (%)", 0.1, 5.0, 1.0)
    
    if st.sidebar.button("Save Strategy"):
        db['UserStates'].update_one(
            {"user_id": st.session_state.logged_in_user},
            {"$set": {"active_symbols": selected, "risk_value": risk}}
        )
        st.sidebar.success("Settings Syncing...")

# Auto-refresh
if st.session_state.logged_in_user:
    time.sleep(10)
    st.rerun()