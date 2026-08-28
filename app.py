import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta

st.set_page_config(layout="wide", page_title="V21 FIX LEMBUR")
st.title("💰 GAJI V21 - LEMBUR X1.5 & X2")

@st.cache_resource
def connect():
    scope = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(creds)
    sh = client.open("REKAP")
    return sh.worksheet("REKAP ABSENSI"), sh.worksheet("DATABASE KARYAWAN"), sh.worksheet("DATA GAJI")

ws_absen, ws_db, ws_gaji = connect()

@st.cache_data(ttl=60)
def load():
    db = pd.DataFrame(ws_db.get_all_records())
    db.columns = [c.strip().upper() for c in db.columns]
    db['ID KARYAWAN'] = db['ID KARYAWAN'].astype(str).str.zfill(8)
    absen = pd.DataFrame(ws_absen.get_all_records())
    absen.columns = [c.strip().upper() for c in absen.columns]
    absen['ID KARYAWAN'] = absen['ID KARYAWAN'].astype(str).str.zfill(8)
    absen['TANGGAL'] = pd.to_datetime(absen['TANGGAL'], errors='coerce')
    return db, absen

db_df, absen_df = load()

def hitung_split(tgl, masuk, pulang):
    """Aturan: Sabtu 5 jam efektif, Senin-Jumat 7 jam. Lembur: jam ke-1 x1.5, jam ke-2+ x2"""
    try:
        fmt = "%H:%M"
        if ":" not in masuk or ":" not in pulang: return 0,0,0
        m = datetime.strptime(masuk.strip(), fmt)
        p = datetime.strptime(pulang.strip(), fmt)
        if p < m: p += timedelta(days=1)
        total = (p - m).total_seconds()/3600 - 1 # -1 jam istirahat
        
        is_sabtu = tgl.weekday() == 5
        efektif = 5 if is_sabtu else 7
        
        if total <= efektif:
            return efektif if total>0 else 0, 0, 0, 0 # jam kerja, lembur total, l1.5, l2.0
        
        lembur = total - efektif
        if is_sabtu:
            # Sabtu full x2
            return efektif, lembur, 0, lembur
        else:
            # Senin-Jumat: jam pertama 1.5, sisanya 2.0
            l15 = 1 if lembur >= 1 else lembur
            l20 = max(0, lembur - 1)
            return efektif, lembur, l15, l20
    except:
        return 7,0,0,0

def to_float(x):
    try: return float(str(x).replace(',','.').strip())
    except: return 0

# SIDEBAR
with st.sidebar:
    menu = st.radio("MENU", ["📅 ABSEN", "💰 GAJI", "🔧 ADMIN EDIT"])

if menu == "📅 ABSEN":
    st.subheader("Input Absen - Cuma Jam Masuk/Pulang")
    with st.form("absen"):
        c1,c2 = st.columns(2)
        with c1:
            idk = st.selectbox("ID", db_df['ID KARYAWAN'].tolist())
            tgl = st.date_input("Tanggal", datetime(2026,8,29))
            shift = st.selectbox("Shift", ["H-S1","H-S2","H-S3","H-LS","T","A"])
        with c2:
            jm = st.text_input("Jam Masuk (07:02)", "07:00")
            jp = st.text_input("Jam Pulang (16:30)", "15:00")
        if st.form_submit_button("SIMPAN", type="primary", use_container_width=True):
            jk, jl, l15, l20 = hitung_split(tgl, jm, jp)
            st.info(f"Hasil: Kerja {jk} jam | Lembur {jl} jam -> 1.5x={l15} jam, 2.0x={l20} jam")
            ws_absen.append_row([idk, str(tgl), jm, jp, jk, jl, l15, l20, shift])
            st.success("✅ Kesimpan! Cek di Google Sheet, udah gak 120:00:00 lagi")
            st.cache_data.clear()

elif menu == "🔧 ADMIN EDIT":
    st.subheader("Benerin data yang 120:00:00 di SS mu")
    if st.button("🔥 HAPUS BARIS 16-17 YANG ERROR 120:00:00", type="primary"):
        ws_absen.delete_rows(16, 17)
        st.success("Udah kehapus! Sekarang input ulang tgl 29-08-2026")
        st.cache_data.clear()

else:
    # GAJI
    bulan = st.selectbox("Bulan", range(1,13), index=7)
    idp = st.selectbox("Karyawan", db_df['ID KARYAWAN'].tolist())
    if st.button("HITUNG GAJI + LEMBUR X1.5 X2", type="primary", use_container_width=True):
        absen_bulan = absen_df[(absen_df['TANGGAL'].dt.month==bulan)].copy()
        data_kar = absen_bulan[absen_bulan['ID KARYAWAN']==idp].copy()
        
        l15_tot = 0; l20_tot = 0
        for _,r in data_kar.iterrows():
            if pd.isna(r['TANGGAL']): continue
            jk, jl, l15, l20 = hitung_split(r['TANGGAL'], str(r.get('JAM MASUK','')), str(r.get('JAM PULANG','')))
            l15_tot += l15; l20_tot += l20

        gaji = 5252909
        rate = gaji/173
        total_lembur = (l15_tot*rate*1.5) + (l20_tot*rate*2.0)
        st.metric("Total Lembur 1.5x", f"{l15_tot} jam")
        st.metric("Total Lembur 2.0x (Sabtu 5 jam)", f"{l20_tot} jam")
        st.metric("Uang Lembur", f"Rp {int(total_lembur):,}")
        st.caption(f"Rumus: ({l15_tot} x {int(rate)} x 1.5) + ({l20_tot} x {int(rate)} x 2.0)")
