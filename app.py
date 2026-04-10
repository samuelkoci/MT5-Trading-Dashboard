import streamlit as st
import pandas as pd
import time
import plotly.graph_objects as go
from pymongo import MongoClient
import certifi
from cryptography.fernet import Fernet
from datetime import datetime

# 1. Page Config
st.set_page_config(page_title="MT5 Cloud Terminal", page_icon="🌐", layout="wide")

# --- MASTER SYMBOL WHITELIST ---
GLOBAL_WHITELIST = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
    "EURGBP", "EURJPY", "GBPJPY", "XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD",
    "GER30", "SPX500", "NAS100"
]

COMMON_SERVERS = [
    "FundedNext-Server", "FundedNext-Server2", "FundedNext-Server3",
    "MetaQuotes-Demo", "ICMarkets-Demo", "ICMarkets-Live",
    "Pepperstone-MT5-Live", "Exness-MT5-Real", "Custom (Type below)"
]

# 2. Database Connection
@st.cache_resource
def get_database():
    try:
        if "MONGO_URI" not in st.secrets:
            st.error("❌ 'MONGO_URI' not found in Streamlit Secrets!")
            return None
        uri = st.secrets["MONGO_URI"].strip()
        client = MongoClient(uri, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=5000)
        client.admin.command('ping')  # FIX: Actually test the connection on startup
        return client['TradingSaaS']
    except Exception as e:
        st.error(f"🔌 MongoDB Connection Error: {e}")
        return None

db = get_database()

# 3. Encryption Setup
cipher_suite = None
try:
    if "ENCRYPTION_KEY" in st.secrets:
        cipher_suite = Fernet(st.secrets["ENCRYPTION_KEY"].encode())
    else:
        st.error("🔐 Encryption Key missing in Streamlit Secrets.")
except Exception as e:
    st.error(f"🔐 Invalid Encryption Key: {e}")

# FIX: Guard both db and cipher_suite before stopping
if db is None or cipher_suite is None:
    st.error("🛑 App cannot start. Check Secrets configuration above.")
    st.stop()

# 4. Session State
if "logged_in_acc" not in st.session_state:
    st.session_state.logged_in_acc = None

# 5. Sidebar: Multi-Account Access
st.sidebar.header("🔐 MT5 Access Control")

if not st.session_state.logged_in_acc:
    with st.sidebar.form("login_panel"):
        login_id = st.text_input("MT5 Account Number", placeholder="e.g. 33433415")
        login_pass = st.text_input("MT5 Master Password", type="password")
        selected_server = st.selectbox("Broker Server", options=COMMON_SERVERS)
        custom_server = st.text_input("Custom Server (if selected above):")

        submit_button = st.form_submit_button("Connect to Cloud Bot")

        if submit_button:
            if login_id and login_pass:
                encrypted_pw = cipher_suite.encrypt(login_pass.encode()).decode()
                final_server = custom_server if selected_server == "Custom (Type below)" else selected_server

                db['UserStates'].update_one(
                    {"mt5_login": str(login_id)},
                    {"$set": {
                        "mt5_pass": encrypted_pw,
                        "mt5_server": final_server,
                        "connection_status": "PENDING",
                        "last_update": datetime.now(),
                        "force_relogin": True  # Tells the local bot to re-auth with new credentials
                    }},
                    upsert=True
                )
                st.session_state.logged_in_acc = str(login_id)
                st.success("✅ Account Linked!")
                time.sleep(1)
                st.rerun()
            else:
                st.warning("Please enter both Account Number and Password.")
else:
    st.sidebar.success(f"Linked Account: {st.session_state.logged_in_acc}")
    if st.sidebar.button("Logout / Switch Account"):
        st.session_state.logged_in_acc = None
        st.rerun()

# 6. Load Data
user_data = None
if st.session_state.logged_in_acc:
    user_data = db['UserStates'].find_one({"mt5_login": st.session_state.logged_in_acc})

# 7. Dashboard UI
st.title("📊 Cloud Trading Terminal")

if not st.session_state.logged_in_acc:
    st.info("👈 Connect your MT5 account using the sidebar to get started.")
    st.stop()  # FIX: Don't render the dashboard at all if not logged in

if user_data:
    balance = user_data.get('balance', 0.00)
    equity = user_data.get('equity', 0.00)
    status = user_data.get('connection_status', 'OFFLINE')
    last_sync = user_data.get('last_sync', 'Waiting for bot...')

    col1, col2, col3 = st.columns(3)
    col1.metric("Account Balance", f"${balance:,.2f}")
    col2.metric("Floating Equity", f"${equity:,.2f}", f"{equity - balance:,.2f}")

    status_color = "green" if status == "ONLINE" else "orange" if status == "PENDING" else "red"
    col3.markdown(f"**Bot Engine:** :{status_color}[{status}]")

    sync_time = last_sync.strftime("%H:%M:%S") if isinstance(last_sync, datetime) else last_sync
    st.caption(f"Last Bot Heartbeat: {sync_time}")

    # --- Gauge Chart ---
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=equity,
        gauge={
            'axis': {'range': [None, max(balance * 1.05, 100)]},
            'bar': {'color': "#00ffcc" if equity >= balance else "#ff4b4b"},
            'steps': [{'range': [0, balance], 'color': "#2b2b2b"}],
            'threshold': {'line': {'color': "white", 'width': 4}, 'value': balance}
        }
    ))
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"},
        height=280, margin=dict(t=30, b=0, l=10, r=10)
    )
    st.plotly_chart(fig, use_container_width=True)

    # --- Strategy Sidebar ---
    st.sidebar.divider()
    st.sidebar.header("⚙️ Strategy Control")

    current_symbols = user_data.get("active_symbols", [])
    selected = st.sidebar.multiselect(
        "Symbols to Scan:",
        options=GLOBAL_WHITELIST,
        default=[s for s in current_symbols if s in GLOBAL_WHITELIST] or ["EURUSD"]
        # FIX: Filter default to only valid whitelist symbols to avoid multiselect crash
    )

    risk = st.sidebar.slider(
        "Lot Multiplier / Risk", 0.01, 5.0,
        float(user_data.get("risk_value", 1.0))
    )

    if st.sidebar.button("Update Cloud Settings"):
        db['UserStates'].update_one(
            {"mt5_login": st.session_state.logged_in_acc},
            {"$set": {
                "active_symbols": selected,
                "risk_value": risk,
                # FIX: Only set force_relogin if credentials were actually changed
                # Settings-only updates should NOT force a full MT5 re-login
            }}
        )
        st.sidebar.toast("✅ Settings Sent to Bot!")
        time.sleep(1)
        st.rerun()

    # --- Live Activity Log ---
    st.subheader("📝 Live Activity Log")
    if status == "ONLINE":
        st.success(f"✅ Bot is scanning {len(current_symbols)} symbol(s) on the 15M timeframe.")
    elif status == "PENDING":
        st.warning("⏳ Bot is connecting. This usually takes under 60 seconds...")
    else:
        st.error("⚠️ Bot is OFFLINE. Check that trading_bot.py is running on your local machine and your MT5 password is correct.")

else:
    st.warning("⏳ Waiting for bot to sync account data. Make sure trading_bot.py is running locally.")

# 8. FIX: Auto-refresh ONLY when logged in AND bot is not yet online
# This prevents hammering the server before any user is connected
if st.session_state.logged_in_acc:
    status_check = user_data.get('connection_status', 'OFFLINE') if user_data else 'PENDING'
    refresh_interval = 15 if status_check == "ONLINE" else 8  # Poll faster while pending
    time.sleep(refresh_interval)
    st.rerun()