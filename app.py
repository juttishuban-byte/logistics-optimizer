import streamlit as st

st.set_page_config(page_title="Logistics Optimizer", layout="wide")

st.title("🚛 Risk-Aware Route Optimizer")
st.write("Server is running! This is where we will compare Dijkstra vs. Greedy.")

# Sidebar for inputs
with st.sidebar:
    st.header("Settings")
    risk_weight = st.slider("Risk Sensitivity", 0.0, 1.0, 0.5)
    st.info(f"Current Weight: {risk_weight}")