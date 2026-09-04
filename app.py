import streamlit as st, gspread, pandas as pd
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="APK ABSENSI", layout="wide")
st.title("APK ABSENSI")

scope = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
client = gspread.authorize(creds)
sh = client.open("REKAP")
ws = sh.worksheet("REKAP ABSENSI")
ws_gaji = sh.worksheet("DATA GAJI")

vals = ws.get_all_values()
df = pd.DataFrame(vals[1:], columns=vals[0])
df['JAM LEMBUR'] = pd.to_numeric(df['JAM LEMBUR'], errors='coerce').fillna(0)

tab1, tab2 = st.tabs(["ABSENSI", "GAJI"])

with tab1:
    st.dataframe(df)

with tab2:
    hadir = len(df[df['STATUS']=='H'])
    lembur = df['JAM LEMBUR'].sum()
    shift = len(df[df['SHIFT'].astype(str).str.contains('S2|S3', na=False)])
    h_lembur = len(df[df['JAM LEMBUR']>0])

    st.metric("Hadir", f"{hadir} Hari")
    st.metric("Lembur", f"{lembur} Jam")
    st.metric("Shift", f"{shift} Hari")

    gaji = 5252909
    um = hadir * 9500
    ul = lembur * 30000
    us = shift * 2187
    uml = h_lembur * 9500
    pend = gaji + 50000 + um + ul + us + uml + 3500 + 12606 + 15758 + 194357 + 105058 + 210116
    pot = 12606 + 15758 + 194357 + 105058 + 210116 + 105058 + 52529 + 52529
    total = pend - pot

    st.metric("TOTAL GAJI", f"Rp {total:,}")
    st.write(f"Rumus: {hadir}x9500 + {lembur}x30000 + {shift}x2187 = Rp {total:,}")

    if st.button("UPDATE KE SHEET DATA GAJI", type="primary", use_container_width=True):
        ws_gaji.batch_update([
            {'range': 'C5', 'values': [[um]]},
            {'range': 'C7', 'values': [[int(ul)]]},
            {'range': 'B8', 'values': [[f"{shift} Hari x 2187"]]},
            {'range': 'C8', 'values': [[int(us)]]},
            {'range': 'C9', 'values': [[uml]]},
            {'range': 'C17', 'values': [[int(pend)]]},
            {'range': 'E17', 'values': [[int(pot)]]},
            {'range': 'C19', 'values': [[int(total)]]},
        ])
        st.success(f"Done! Sheet mu sekarang {total} - gak ERROR lagi!")
        st.balloons()
