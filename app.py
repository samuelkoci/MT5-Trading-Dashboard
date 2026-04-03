import streamlit as st
import pandas as pd
import time
import plotly.graph_objects as go
from pymongo import MongoClient
import certifi

# 1. Page Configuration
st.set_page_config(page_title="Universal MT5 Multi-Monitor", page_icon="🌐", layout="wide")

# 2. Database Connection
# Replace <db_password> with your actual password.
# PRO TIP: On Streamlit Cloud, move this to 'Settings > Secrets' for safety!
MONGO_URI = "mongodb+srv://smlkoci_db_user:<db_password>@cluster0.wvogs9k.mongodb.net/?appName=Cluster0"

@st.cache_resource
def get_database():
    client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
    return client['TradingSaaS']

db = get_database()
collection = db['UserStates']

# 3. Sidebar: User & Strategy Settings
st.sidebar.header("👤 User Account")
user_id = st.sidebar.text_input("Enter Account ID", value="Trader_01")

# Fetch data from MongoDB for this specific user
user_data = collection.find_one({"user_id": user_id})

st.sidebar.divider()
st.sidebar.header("⚙️ Strategy Control")

if user_data and "mt5_catalog" in user_data:
    # --- DYNAMIC SYMBOL SELECTION ---
    # We pull the list directly from the user's MT5 terminal catalog
    catalog = user_data["mt5_catalog"]
    current_active = user_data.get("active_symbols", ["EURUSD"])
    
    selected_symbols = st.sidebar.multiselect(
        "Active Symbols", 
        options=catalog, 
        default=current_active
    )

    # --- ADAPTIVE RISK INPUT ---
    st.sidebar.subheader("Risk Management")
    risk_type = st.sidebar.selectbox("Risk Mode", ["Dynamic (Lots per $1k)", "Fixed Dollars", "Fixed Lots"])

    if risk_type == "Dynamic (Lots per $1k)":
        risk_value = st.sidebar.slider("Lot Multiplier", 0.01, 0.50, 0.05)
    elif risk_type == "Fixed Dollars":
        risk_value = st.sidebar.number_input("USD Risk per Trade", 10, 5000, 100)
    else:
        risk_value = st.sidebar.number_input("Static Lot Size", 0.01, 10.0, 0.1)

    # --- SAVE TO CLOUD ---
    if st.sidebar.button("💾 Apply & Sync to MT5"):
        # We push a 'new_settings' packet that the bot will 'read' and apply
        new_config = {
            "symbols": selected_symbols,
            "risk_mode": risk_type.lower().split(" ")[0], # dynamic, fixed, static
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
if user_data:
    st.markdown(f"**Live Feed for:** `{user_id}` | *Last Heartbeat: {user_data.get('last_update', 'N/A')}*")
else:
    st.markdown(f"**Live Feed for:** `{user_id}` | *Status: Disconnected*")
st.divider()

if user_data:
    # --- ROW 1: Key Metrics ---
    col1, col2, col3, col4 = st.columns(4)
    
    # Calculate Profit Color
    p_color = "normal" if user_data['profit'] >= 0 else "inverse"
    
    col1.metric("Account Balance", f"${user_data['balance']:,.2f}")
    col2.metric("Current Equity", f"${user_data['equity']:,.2f}", f"{user_data['profit']:,.2f}", delta_color=p_color)
    col3.metric("Symbols Selected", len(user_data.get("active_symbols", [])))
    col4.metric("Currency", user_data.get("currency", "USD"))

    # --- ROW 2: Gauges & Strategy Details ---
    st.subheader("Account Health")
    g_col1, g_col2 = st.columns([2, 1])

    with g_col1:
        # Professional Gauge using live balance/equity
        fig = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = user_data['equity'],
            domain = {'x': [0, 1], 'y': [0, 1]},
            title = {'text': "Live Equity Monitor"},
            gauge = {
                'axis': {'range': [user_data['balance']*0.8, user_data['balance']*1.2]},
                'bar': {'color': "#00ffcc"},
                'steps': [
                    {'range': [0, user_data['balance']], 'color': "#2a2a2a"},
                    {'range': [user_data['balance'], user_data['balance']*1.2], 'color': "#004d40"}
                ],
                'threshold': {
                    'line': {'color': "white", 'width': 4},
                    'value': user_data['balance']
                }
            }
        ))
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"}, height=400)
        st.plotly_chart(fig, use_container_width=True)

    with g_col2:
        st.info("**Active Symbols in Algo**")
        st.code("\n".join(user_data.get("active_symbols", ["None"])))
        if st.button("🔄 Refresh Data"):
            st.rerun()

else:
    st.warning(f"⚠️ No active connection found for `{user_id}`.")
    st.info("Start your local `trading_bot.py` to begin streaming data.")

# 5. Auto-Refresh (every 30 seconds for Cloud efficiency)
time.sleep(30)
st.rerun()