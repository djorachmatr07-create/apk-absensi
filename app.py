import streamlit as st
import gspread
import requests
import pandas as pd
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="APK ABSENSI V1", layout="wide")
st.title("📍 APK ABSENSI KARYAWAN V4.4")

PASSWORD_ADMIN = "admin123"

MASTER_KODE = {
    "H": {"nama": "HADIR", "gaji": "100%", "jam": "Sesuai jam kerja"},
    "A": {"nama": "ALPA", "gaji": "0%", "jam": "0 jam. Potong 1 hari"},
    "I": {"nama": "IZIN", "gaji": "0% - 50%", "jam": "0 jam"},
    "S": {"nama": "SAKIT", "gaji": "100% - 75%", "jam": "0 jam. 3 hari pertama full"},
    "C": {"nama": "CUTI", "gaji": "100%", "jam": "0 jam. Jatah 12 hari/tahun"},
    "L": {"nama": "LIBUR", "gaji": "100%", "jam": "0 jam"},
    "GH": {"nama": "GANTI HARI BIASA", "gaji": "100%", "jam": "Efektif 7 jam"},
    "GHS": {"nama": "GANTI HARI SABTU", "gaji": "100%", "jam": "Efektif 5 jam"},
    "OT": {"nama": "LEMBUR", "gaji": "1.5x - 2x", "jam": "Tambah jam lembur"},
    "TL": {"nama": "TERLAMBAT", "gaji": "100%", "jam": "Jam kerja - jam telat"},
    "PC": {"nama": "PULANG CEPAT", "gaji": "100%", "jam": "Jam kerja - jam PC"},
    "SH": {"nama": "SETENGAH HARI", "gaji": "50%", "jam": "4 jam"},
    "DL": {"nama": "DINAS LUAR", "gaji": "100%", "jam": "Tetap 8 jam"},
    "WFH":{"nama": "WORK FROM HOME", "gaji": "100%", "jam": "Tetap 8 jam jika target tercapai"},
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

@st.cache_data(ttl=300)
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

@st.cache_data(ttl=86400)
def get_libur(tahun):
    try:
        res = requests.get(f"https://indonesia-holiday-api.vercel.app/api/{tahun}", timeout=5)
        data = res.json()
        return {i['holiday_date']: i['holiday_name'] for i in data}
    except: return {}

LIBUR_DICT = {}
LIBUR_DICT.update(get_libur(2025))
LIBUR_DICT.update(get_libur(2026))

def hitung(masuk_dt, pulang_dt, status):
    tgl = masuk_dt.strftime('%Y-%m-%d')
    weekday = masuk_dt.weekday()
    is_tgl_merah = tgl in LIBUR_DICT
    is_minggu = weekday == 6
    is_sabtu = weekday == 5

    if status == "L":
        shift = "L"
        jam_kerja = "0:00:00"
        jam_lembur = "0.00"
        if is_tgl_merah:
            keterangan = f"LIBUR NASIONAL: {LIBUR_DICT[tgl]}"
        elif is_minggu:
            keterangan = "LIBUR MINGGU"
        else:
            keterangan = "LIBUR"
    elif status == "A":
        shift, jam_kerja, jam_lembur, keterangan = "A", "0:00:00", "0.00", "A"
    else: # H
        shift, jam_kerja, jam_lembur, keterangan = "SHIFT 2", "7:00:00", "0.00", "HARI KERJA"

    return jam_kerja, jam_lembur, shift, keterangan, masuk_dt.strftime('%d/%m/%Y %H:%M:%S'), pulang_dt.strftime('%d/%m/%Y %H:%M:%S')

def upsert_absen(id_kar, masuk_dt, pulang_dt, nama, status="H"):
    id_kar = id_kar.zfill(8)
    tgl_str = masuk_dt.strftime('%d/%m/%Y')
    jam_kerja, jam_lembur, shift, ket, jam_masuk_str, jam_pulang_str = hitung(masuk_dt, pulang_dt, status)
    row_data = [id_kar, nama, jam_masuk_str, jam_pulang_str, jam_kerja, jam_lembur, shift, ket, status]

    if not absen_df.empty:
        existing = absen_df[(absen_df['ID KARYAWAN'] == id_kar) & (absen_df['JAM MASUK DT'].dt.strftime('%d/%m/%Y') == tgl_str)]
    else:
        existing = pd.DataFrame()

    if not existing.empty:
        row_num = existing.index[0] + 2
        ws_absen.update(f'A{row_num}:I{row_num}', [row_data], value_input_option='USER_ENTERED') # UPDATE 1 BARIS PENUH
    else:
        ws_absen.insert_row(row_data, 2, value_input_option='USER_ENTERED')
    load_data.clear()

def update_keterangan_libur():
    if absen_df.empty: return 0
    progress = st.progress(0)
    count = 0
    data_l = absen_df[absen_df['STATUS'] == 'L'].copy()
    total = len(data_l)
    st.write(f"Ketemu {total} data L. Mulai update...")

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
            # AMBIL DATA LAMA 1 BARIS PENUH LALU TIMPA KOLOM G H
            row_lama = ws_absen.row_values(row_num)
            row_lama[6] = "L" # Kolom G = SHIFT
            row_lama[7] = ket_baru # Kolom H = KETERANGAN
            ws_absen.update(f'A{row_num}:I{row_num}', [row_lama], value_input_option='USER_ENTERED')
            count += 1
        except Exception as e:
            st.error(f"Error baris {row_num}: {e}")
        progress.progress((i + 1) / total)
    load_data.clear()
    return count

menu = st.tabs(["📝 ABSEN", "✏️ EDIT DATA", "⚙️ ADMIN"])

with menu[2]:
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 UPDATE KETERANGAN LIBUR", use_container_width=True, type="primary"):
            with st.spinner("Sedang update semua data L..."):
                jml = update_keterangan_libur()
            st.success(f"✅ Selesai! {jml} data L diupdate keterangannya")
            st.rerun()
    with col2:
        if st.button("🗑️ REFRESH DATA", use_container_width=True):
            load_data.clear()
            st.rerun()

    if not absen_df.empty:
        st.dataframe(absen_df.sort_values('JAM MASUK DT', ascending=False), use_container_width=True)
