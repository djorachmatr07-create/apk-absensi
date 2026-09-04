import streamlit as st, gspread, pandas as pd
from google.oauth2.service_account import Credentials
from datetime import datetime

st.set_page_config(page_title="APK ABSENSI", layout="wide")
st.title("APK ABSENSI")

scope = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
client = gspread.authorize(creds)
sh = client.open("REKAP")
ws = sh.worksheet("REKAP ABSENSI")
ws_gaji = sh.worksheet("DATA GAJI")

def load():
    v = ws.get_all_values()
    return pd.DataFrame(v[1:], columns=v[0])

df = load()
df['JAM LEMBUR'] = pd.to_numeric(df['JAM LEMBUR'], errors='coerce').fillna(0)

tab1, tab2, tab3 = st.tabs(["📋 DATA", "➕ ABSEN", "💰 GAJI"])

with tab1:
    st.dataframe(df, use_container_width=True)
    if st.button("🔄 Reload"): st.rerun()

with tab2:
    st.subheader("Absen Cepat")
    # AUTO ID & NAMA biar gak ribet
    with st.form("simple"):
        tgl = st.date_input("Tanggal", datetime.now())
        shift = st.selectbox("Shift", ["S1 (07-16)", "S2 (15-23)", "S3 (23-07)"])
        status = st.radio("Status", ["H","A","I","S"], horizontal=True)
        lembur = st.number_input("Lembur (Jam)", 0.0, 10.0, 0.0, 0.5)

        # Auto jam berdasarkan shift
        jam_map = {"S1 (07-16)": ("07:00:00","16:00:00"), "S2 (15-23)": ("15:00:00","23:00:00"), "S3 (23-07)": ("23:00:00","07:00:00")}
        jm, jp = jam_map[shift]
        shift_code = shift[:2]

        st.info(f"Auto: {jm} - {jp} | Shift {shift_code}")
        simpan = st.form_submit_button("SIMPAN", type="primary", use_container_width=True)
        if simpan:
            ws.append_row(["01213027","RACHMAT RAHARDJO",str(tgl),jm,jp,lembur,shift_code,status])
            st.success("Tersimpan!")
            st.rerun()

with tab3:
    hadir = len(df[df['STATUS']=='H'])
    lembur = df['JAM LEMBUR'].sum()
    s = len(df[df['SHIFT'].astype(str).str.contains('S2|S3', na=False)])
    hl = len(df[df['JAM LEMBUR']>0])

    st.metric("Hadir", f"{hadir} Hari")
    st.metric("Lembur", f"{lembur} Jam")
    st.metric("Shift Malam", f"{s} Hari")

    total = 5252909 + 50000 + hadir*9500 + lembur*30000 + s*2187 + hl*9500 + 3500 + 12606 + 15758 + 194357 + 105058 + 210116 - (12606+15758+194357+105058+210116+105058+52529+52529)
    st.metric("Total Gaji", f"Rp {total:,}")

    if st.button("Update ke Sheet Gaji", type="primary", use_container_width=True):
        ws_gaji.batch_update([
            {'range': 'C5', 'values': [[hadir*9500]]},
            {'range': 'C7', 'values': [[int(lembur*30000)]]},
            {'range': 'C8', 'values': [[int(s*2187)]]},
            {'range': 'C9', 'values': [[hl*9500]]},
            {'range': 'C19', 'values': [[int(total)]]},
        ])
        st.success(f"Done Rp {total:,}")
        st.balloons()

# Edit tetep bisa dari tab DATA - tinggal klik ikon pensil di tabel atas
