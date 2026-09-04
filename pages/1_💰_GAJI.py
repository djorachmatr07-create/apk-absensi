import streamlit as st, gspread, pandas as pd
from google.oauth2.service_account import Credentials

st.title("💰 GAJI - TEST NYALA")
st.success("Kalau ini muncul, berarti udah gak hitam lagi!")

scope = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
client = gspread.authorize(creds)
sh = client.open("REKAP")
ws = sh.worksheet("REKAP ABSENSI")
vals = ws.get_all_values()
df = pd.DataFrame(vals[1:], columns=vals[0])
st.write(f"Total baris: {len(df)}")
st.dataframe(df.head())

# RUMUS LENGKAP ANTI #ERROR!
hadir = len(df[df['STATUS']=='H'])
total_lembur = pd.to_numeric(df['JAM LEMBUR'], errors='coerce').fillna(0).sum()
shift = len(df[df['SHIFT'].str.contains('S2|S3', na=False)])
st.metric("Hadir", f"{hadir} Hari")
st.metric("Lembur", f"{total_lembur} Jam")
st.metric("Shift", f"{shift} Hari")
st.metric("Total Gaji Estimasi", f"Rp {5252909 + hadir*9500 + total_lembur*30000 + shift*2187:,}")
