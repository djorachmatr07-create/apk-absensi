import streamlit as st
st.set_page_config(layout="wide")
st.title("💰 REKAP - MODE DARURAT")
st.success("App nyala lagi! Kalau ini kelihatan, berarti fix berhasil.")

import gspread, pandas as pd
from google.oauth2.service_account import Credentials

scope = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
client = gspread.authorize(creds)
sh = client.open("REKAP")
ws = sh.worksheet("REKAP ABSENSI")
data = ws.get_all_values()
st.write(f"Data REKAP ABSENSI: {len(data)-1} baris")
st.dataframe(data[:20])
