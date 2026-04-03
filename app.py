import streamlit as st
import pandas as pd
import time
import plotly.graph_objects as go
from pymongo import MongoClient
import certifi

# 1. Page Configuration
st.set_page_config(page_title="Universal MT5 Multi-Monitor", page_icon="📊", layout="wide")

# 2. Database Connection
# Replace the MONGO_URI line with st.secrets["MONGO_URI"] when moving to Streamlit Cloud
MONGO_URI = st.secrets["MONGO_URI"]

@st.cache_resource
def get_database():
    try:
        # Use the secret directly
        client = MongoClient(
            st.secrets["MONGO_URI"], 
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=5000,
            # This ensures we don't use a stale, cached connection
            connect=True 
        )
        # FORCE an authentication check right now
        client.admin.command('ping') 
        return client['TradingSaaS']
    except Exception as e:
        # This will show us exactly what's wrong on the screen
        st.error(f"⚠️ MongoDB Auth Error: {e}")
        return None

# 3. Sidebar: User & Strategy Settings
st.sidebar.header("👤 User Account")
user_id = st.sidebar.text_input("Enter Account ID", value="Trader_01")

if db is not None:
    collection = db['UserStates']
    user_data = collection.find_one({"user_id": user_id})

    st.sidebar.divider()
    st.sidebar.header("⚙️ Strategy Control")

    if user_data and "mt5_catalog" in user_data:
        # Dynamic Symbol Selection from your actual MT5 terminal
        catalog = user_data["mt5_catalog"]
        current_active = user_data.get("active_symbols", [])
        
        selected_symbols = st.sidebar.multiselect(
            "Active Symbols", 
            options=catalog, 
            default=current_active if current_active else catalog[:3]
        )

        # Risk Management
        st.sidebar.subheader("Risk Management")
        risk_type = st.sidebar.selectbox("Risk Mode", ["Dynamic (Lots per $1k)", "Fixed Dollars", "Fixed Lots"])
        risk_value = st.sidebar.number_input("Risk Value", value=0.05, step=0.01)

        # Apply Settings
        if st.sidebar.button("💾 Apply & Sync to MT5"):
            new_config = {
                "symbols": selected_symbols,
                "risk_mode": risk_type.lower().split(" ")[0],
                "risk_value": risk_value
            }
            collection.update_one(
                {"user_id": user_id},
                {"$set": {"new_settings": new_config}}
            )
            st.sidebar.success("Settings pushed to Cloud! 📡")
    else:
        st.sidebar.warning("Waiting for Bot to upload MT5 Catalog...")

# 4. Main Dashboard UI
st.title("📊 Universal MT5 Multi-Monitor")
if db is not None and user_data:
    st.markdown(f"**Live Feed for:** `{user_id}` | *Last Heartbeat: {user_data.get('last_update', 'N/A')}*")
    st.divider()

    # --- ROW 1: Key Metrics ---
    col1, col2, col3, col4 = st.columns(4)
    p_color = "normal" if user_data.get('profit', 0) >= 0 else "inverse"
    
    col1.metric("Account Balance", f"${user_data.get('balance', 0):,.2f}")
    col2.metric("Current Equity", f"${user_data.get('equity', 0):,.2f}", f"{user_data.get('profit', 0):,.2f}", delta_color=p_color)
    col3.metric("Symbols Selected", len(user_data.get("active_symbols", [])))
    col4.metric("Currency", user_data.get("currency", "USD"))

    # --- ROW 2: Equity Gauge ---
    st.subheader("Account Health")
    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = user_data.get('equity', 0),
        domain = {'x': [0, 1], 'y': [0, 1]},
        gauge = {
            'axis': {'range': [user_data.get('balance', 0)*0.8, user_data.get('balance', 0)*1.2]},
            'bar': {'color': "#00ffcc"},
            'steps': [
                {'range': [0, user_data.get('balance', 0)], 'color': "#2a2a2a"},
            ],
            'threshold': {'line': {'color': "white", 'width': 4}, 'value': user_data.get('balance', 0)}
        }
    ))
    fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"}, height=400)
    st.plotly_chart(fig, use_container_width=True)

else:
    st.info("👋 Welcome! Please start your MT5 Trading Bot to see live data.")

# Auto-Refresh
time.sleep(10)
st.rerun()