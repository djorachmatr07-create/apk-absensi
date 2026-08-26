import streamlit as st
import gspread
import pandas as pd
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="APK ABSENSI V1", layout="wide")
st.title("📍 APK ABSENSI KARYAWAN V4.5")

PASSWORD_ADMIN = "admin123"

# HARDCODE LIBUR NASIONAL 2026 - SK KEMENPAN
LIBUR_DICT = {
    "2026-01-01": "Tahun Baru 2026",
    "2026-01-29": "Tahun Baru Imlek 2577 Kongzili",
    "2026-02-14": "Isra Mikraj Nabi Muhammad SAW",
    "2026-03-19": "Hari Suci Nyepi Tahun Baru Saka 1948",
    "2026-03-20": "Cuti Bersama Hari Suci Nyepi",
    "2026-03-29": "Wafat Isa Al Masih",
    "2026-03-30": "Cuti Bersama Hari Wafat Isa Al Masih",
    "2026-04-21": "Hari Raya Idul Fitri 1447 H",
    "2026-04-22": "Hari Raya Idul Fitri 1447 H",
    "2026-04-23": "Cuti Bersama Hari Raya Idul Fitri 1447 H",
    "2026-04-24": "Cuti Bersama Hari Raya Idul Fitri 1447 H",
    "2026-05-01": "Hari Buruh Internasional",
    "2026-05-14": "Kenaikan Isa Al Masih",
    "2026-05-27": "Hari Raya Waisak 2560 BE",
    "2026-05-28": "Cuti Bersama Hari Raya Waisak",
    "2026-06-01": "Hari Lahir Pancasila",
    "2026-06-17": "Hari Raya Idul Adha 1447 H",
    "2026-06-18": "Cuti Bersama Hari Raya Idul Adha",
    "2026-06-27": "1 Muharram 1448 H - Tahun Baru Islam",
    "2026-08-17": "Hari Kemerdekaan Republik Indonesia",
    "2026-08-28": "Maulid Nabi Muhammad SAW",
    "2026-12-25": "Hari Raya Natal",
}

@st.cache_resource
def connect_gsheet():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(creds)
    sh = client.open("REKAP")
    ws_absen = sh.worksheet("REKAP ABSENSI")
    ws_db = sh.worksheet("DATABASE KARYAWAN")
    return ws_absen, ws_db

ws_absen, ws_db = connect_gsheet()

@st.cache_data(ttl=60) # TTL DIPERCEPAT BIAR CEPAT REFRESH
def load_data():
    db = pd.DataFrame(ws_db.get_all_records())
    db['ID KARYAWAN'] = db['ID KARYAWAN'].astype(str).str.zfill(8)
    absen = pd.DataFrame(ws_absen.get_all_records())
    if not absen.empty:
        absen['ID KARYAWAN'] = absen['ID KARYAWAN'].astype(str).str.zfill(8)
        absen['JAM MASUK DT'] = pd.to_datetime(absen['JAM MASUK'], format='%d/%m/%Y %H:%M:%S', errors='coerce')
        if 'STATUS' not in absen.columns:
            absen['STATUS'] = 'H'
    else:
        absen = pd.DataFrame(columns=["ID KARYAWAN", "NAMA KARYAWAN", "JAM MASUK", "JAM PULANG", "JAM KERJA", "JAM LEMBUR", "SHIFT", "KETERANGAN", "STATUS", "JAM MASUK DT"])
    return db, absen

db_df, absen_df = load_data()
st.success(f"✅ Konek. Karyawan: {len(db_df)} | Data Absen: {len(absen_df)}")

def update_keterangan_libur():
    if absen_df.empty: return 0
    data_l = absen_df[absen_df['STATUS'] == 'L'].copy()
    if data_l.empty: return 0

    updates = []
    count = 0
    for i, row in data_l.iterrows():
        try:
            masuk_dt = pd.to_datetime(row['JAM MASUK'])
            tgl_str = masuk_dt.strftime('%Y-%m-%d')
            is_tgl_merah = tgl_str in LIBUR_DICT
            is_minggu = masuk_dt.weekday() == 6

            if is_tgl_merah:
                ket_baru = f"LIBUR NASIONAL: {LIBUR_DICT[tgl_str]}"
            elif is_minggu:
                ket_baru = "LIBUR MINGGU"
            else:
                ket_baru = "LIBUR"

            row_num = i + 2
            updates.append({'range': f'G{row_num}:H{row_num}', 'values': [['L', ket_baru]]})
            count += 1
        except: pass

    if updates:
        ws_absen.batch_update(updates, value_input_option='USER_ENTERED') # BATCH UPDATE LEBIH AMAN
    load_data.clear()
    return count

menu = st.tabs(["📝 ABSEN", "✏️ EDIT DATA", "⚙️ ADMIN"])

with menu[2]:
    if st.button("🔄 UPDATE KETERANGAN LIBUR SEKARANG", use_container_width=True, type="primary"):
        with st.spinner("Sedang update semua data L pakai data 2026..."):
            jml = update_keterangan_libur()
        st.success(f"✅ Selesai! {jml} data L diupdate. Cek Sheet")
        st.rerun()

    if not absen_df.empty:
        st.dataframe(absen_df.sort_values('JAM MASUK DT', ascending=False), use_container_width=True)
