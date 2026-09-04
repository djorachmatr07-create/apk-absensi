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

def load_data():
    vals = ws.get_all_values()
    return pd.DataFrame(vals[1:], columns=vals[0])

df = load_data()
df['JAM LEMBUR'] = pd.to_numeric(df['JAM LEMBUR'], errors='coerce').fillna(0)

tab_absen, tab_input, tab_edit, tab_gaji = st.tabs(["📋 ABSENSI", "➕ INPUT ABSEN", "✏️ EDIT / HAPUS", "💰 GAJI"])

with tab_absen:
    st.dataframe(df, use_container_width=True, height=500)

with tab_input:
    st.subheader("Input Absen Baru")
    with st.form("form_absen"):
        c1,c2 = st.columns(2)
        id_kar = c1.text_input("ID KARYAWAN", "01213027")
        nama = c2.text_input("NAMA", "RACHMAT RAHARDJO")
        tgl = c1.date_input("TANGGAL", datetime.now())
        jam_masuk = c2.text_input("JAM MASUK", "07:00:00")
        jam_pulang = c1.text_input("JAM PULANG", "16:00:00")
        shift = c2.selectbox("SHIFT", ["S1","S2","S3"])
        status = c1.selectbox("STATUS", ["H","A","I","S"])
        jam_lembur = c2.number_input("JAM LEMBUR", 0.0, step=0.5)
        if st.form_submit_button("SIMPAN ABSEN", type="primary", use_container_width=True):
            ws.append_row([id_kar, nama, str(tgl), jam_masuk, jam_pulang, jam_lembur, shift, status])
            st.success("Absen tersimpan!")
            st.rerun()

with tab_edit:
    st.subheader("Edit / Hapus - Klik cell nya langsung")
    edited = st.data_editor(df, use_container_width=True, num_rows="dynamic", key="editor")
    c1,c2 = st.columns(2)
    if c1.button("💾 SIMPAN EDIT", type="primary", use_container_width=True):
        ws.clear()
        ws.update([df.columns.values.tolist()] + edited.values.tolist())
        st.success("Edit tersimpan!")
    if c2.button("🔄 RELOAD", use_container_width=True):
        st.rerun()

with tab_gaji:
    st.subheader("HITUNG GAJI - 13 HARI = 5.781.289")
    hadir = len(df[df['STATUS']=='H'])
    lembur = df['JAM LEMBUR'].sum()
    jml_shift = len(df[df['SHIFT'].astype(str).str.contains('S2|S3', na=False)])
    h_lembur = len(df[df['JAM LEMBUR']>0])

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Hadir", f"{hadir} Hari")
    c2.metric("Lembur", f"{lembur} Jam")
    c3.metric("Shift", f"{jml_shift} Hari")
    c4.metric("Hari Lembur", f"{h_lembur} Hari")

    gaji_pokok = 5252909
    um = hadir * 9500
    ul = lembur * 30000
    us = jml_shift * 2187
    uml = h_lembur * 9500
    pend = gaji_pokok + 50000 + um + ul + us + uml + 3500 + 12606 + 15758 + 194357 + 105058 + 210116
    pot = 12606 + 15758 + 194357 + 105058 + 210116 + 105058 + 52529 + 52529
    total = pend - pot

    st.metric("TOTAL GAJI", f"Rp {total:,}", delta=f"{hadir} Hari kerja")

    if st.button("🚀 UPDATE KE SHEET DATA GAJI", type="primary", use_container_width=True):
        ws_gaji.batch_update([
            {'range': 'B5', 'values': [[f"{hadir} Hari x 9500"]]},
            {'range': 'C5', 'values': [[um]]},
            {'range': 'B7', 'values': [[f"{lembur} Jam x 30000"]]},
            {'range': 'C7', 'values': [[int(ul)]]},
            {'range': 'B8', 'values': [[f"{jml_shift} Hari x 2187"]]},
            {'range': 'C8', 'values': [[int(us)]]},
            {'range': 'B9', 'values': [[f"{h_lembur} Hari x 9500"]]},
            {'range': 'C9', 'values': [[uml]]},
            {'range': 'C17', 'values': [[int(pend)]]},
            {'range': 'E17', 'values': [[int(pot)]]},
            {'range': 'C19', 'values': [[int(total)]]},
        ])
        st.success(f"Sheet DATA GAJI udah diupdate! {hadir} Hari = Rp {total:,} - cek Google Sheet, udah gak #ERROR! lagi")
        st.balloons()
