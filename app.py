import streamlit as st
import pandas as pd
import time
import plotly.graph_objects as go
from pymongo import MongoClient
import certifi

# 1. Page Configuration
st.set_page_config(page_title="Universal MT5 Multi-Monitor", page_icon="📊", layout="wide")

# 2. Database Connection Logic
@st.cache_resource
def get_database():
    try:
        # Pulling from Streamlit Secrets (Make sure Avioni12 is in the Secrets tab!)
        uri = st.secrets["MONGO_URI"]
        client = MongoClient(
            uri, 
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=5000
        )
        # Force a connection test
        client.admin.command('ping')
        return client['TradingSaaS']
    except Exception as e:
        st.error(f"🔌 Database Connection Error: {e}")
        return None

# --- INITIALIZE DB ---
db = get_database()
user_data = None  # Default state

# 3. Sidebar: User & Strategy Settings
st.sidebar.header("👤 User Account")
user_id = st.sidebar.text_input("Enter Account ID", value="Trader_01")

if db is not None:
    collection = db['UserStates']
    user_data = collection.find_one({"user_id": user_id})

    st.sidebar.divider()
    st.sidebar.header("⚙️ Strategy Control")

    if user_data and "mt5_catalog" in user_data:
        catalog = user_data["mt5_catalog"]
        current_active = user_data.get("active_symbols", [])
        
        selected_symbols = st.sidebar.multiselect(
            "Active Symbols", 
            options=catalog, 
            default=current_active if current_active else (catalog[:3] if catalog else [])
        )

        st.sidebar.subheader("Risk Management")
        risk_type = st.sidebar.selectbox("Risk Mode", ["Dynamic (Lots per $1k)", "Fixed Dollars", "Fixed Lots"])
        risk_value = st.sidebar.number_input("Risk Value", value=0.05, step=0.01)

        if st.sidebar.button("💾 Apply & Sync to MT5"):
            new_config = {
                "symbols": selected_symbols,
                "risk_mode": risk_type.lower().split(" ")[0],
                "risk_value": risk_value
            }
            collection.update_one(
                {"user_id": user_id},
                {"$set": {"new_settings": new_config}},
                upsert=True
            )
            st.sidebar.success("Settings pushed to Cloud! 📡")
    else:
        st.sidebar.warning("Waiting for Bot to upload MT5 Catalog...")

# 4. Main Dashboard UI
st.title("📊 Universal MT5 Multi-Monitor")

if db is not None and user_data:
    st.markdown(f"**Live Feed for:** `{user_id}` | *Last Update: {user_data.get('last_update', 'N/A')}*")
    st.divider()

    # --- ROW 1: Metrics ---
    col1, col2, col3, col4 = st.columns(4)
    balance = user_data.get('balance', 0)
    equity = user_data.get('equity', 0)
    profit = user_data.get('profit', 0)
    
    col1.metric("Account Balance", f"${balance:,.2f}")
    col2.metric("Current Equity", f"${equity:,.2f}", f"{profit:,.2f}")
    col3.metric("Symbols Active", len(user_data.get("active_symbols", [])))
    col4.metric("Currency", user_data.get("currency", "USD"))

    # --- ROW 2: Equity Gauge ---
    st.subheader("Account Health")
    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = equity,
        gauge = {
            'axis': {'range': [balance * 0.8, balance * 1.2]},
            'bar': {'color': "#00ffcc"},
            'steps': [{'range': [0, balance], 'color': "#2a2a2a"}],
            'threshold': {'line': {'color': "white", 'width': 4}, 'value': balance}
        }
    ))
    fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"}, height=350)
    st.plotly_chart(fig, use_container_width=True)

else:
    st.info("👋 Welcome! Make sure your MT5 Trading Bot is running locally to see live data.")

# Auto-Refresh every 10 seconds
time.sleep(10)
st.rerun()