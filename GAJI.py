import streamlit as st, gspread, pandas as pd
from google.oauth2.service_account import Credentials
st.title("GAJI - TEST NYALA")
st.success("Udah gak hitam lagi min!")
scope = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
client = gspread.authorize(creds)
sh = client.open("REKAP")
ws = sh.worksheet("REKAP ABSENSI")
vals = ws.get_all_values()
df = pd.DataFrame(vals[1:], columns=vals[0])
st.write(f"Total: {len(df)} baris")
st.dataframe(df.head(20))
hadir = len(df[df['STATUS']=='H'])
total_lembur = pd.to_numeric(df['JAM LEMBUR'], errors='coerce').fillna(0).sum()
shift = len(df[df['SHIFT'].str.contains('S2|S3', na=False)])
st.metric("Hadir", f"{hadir} Hari = 13 Hari yang di SS mu")
st.metric("Shift", f"{shift} Hari (yang ERROR tadi)")
