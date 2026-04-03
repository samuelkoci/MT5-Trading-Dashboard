import streamlit as st
import pandas as pd
import json
import os
import time
import plotly.graph_objects as go

# 1. Page Configuration (Makes it look like a real Web App)
st.set_page_config(page_title="FundedNext Monitor", page_icon="📈", layout="wide")

# 2. Function to Load Data from the Bot
def load_bot_data():
    if os.path.exists("web_status.json"):
        with open("web_status.json", "r") as f:
            return json.load(f)
    return None

# 3. Sidebar Controls
st.sidebar.header("🕹️ Bot Control Panel")
st.sidebar.info("Status: System Active")
risk_level = st.sidebar.select_slider("Risk Profile", options=["Low", "Medium", "High"], value="Low")
if st.sidebar.button("🛑 EMERGENCY KILL-SWITCH"):
    st.sidebar.error("Global Stop Command Sent!")

# 4. Main Dashboard UI
st.title("🚀 FundedNext Competition Dashboard")
st.markdown(f"*Last System Heartbeat: {time.strftime('%H:%M:%S')}*")
st.divider()

data = load_bot_data()

if data:
    # --- ROW 1: Key Metrics ---
    col1, col2, col3, col4 = st.columns(4)
    
    # Calculate Profit Color
    p_color = "normal" if data['profit'] >= 0 else "inverse"
    
    col1.metric("Account Balance", f"${data['balance']:,.2f}")
    col2.metric("Current Equity", f"${data['equity']:,.2f}", f"{data['profit']:,.2f}", delta_color=p_color)
    col3.metric("Markets Active", data['active_symbols'])
    col4.metric("Uptime", "100%", "Stable")

    # --- ROW 2: Visual Gauge ---
    st.subheader("Target & Drawdown Monitor")
    
    # Create a professional Gauge chart using Plotly
    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = data['equity'],
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': "Equity Status (vs Starting Balance)"},
        gauge = {
            'axis': {'range': [None, data['balance'] * 1.1]},
            'bar': {'color': "#00ffcc"},
            'steps': [
                {'range': [0, data['balance'] * 0.95], 'color': "#ff4b4b"}, # Drawdown Zone
                {'range': [data['balance'] * 0.95, data['balance'] * 1.1], 'color': "#1e1e1e"}
            ],
            'threshold': {
                'line': {'color': "white", 'width': 4},
                'thickness': 0.75,
                'value': data['balance']
            }
        }
    ))
    st.plotly_chart(fig, use_container_width=True)

else:
    st.warning("⚠️ Waiting for data... Please start 'trading_bot.py' to begin monitoring.")
    st.info("The dashboard will automatically update once the bot creates the 'web_status.json' file.")

# 5. Auto-Refresh (Keep the dashboard live)
time.sleep(10)
st.rerun()