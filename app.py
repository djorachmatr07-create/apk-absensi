import streamlit as st
import gspread
import requests
import pandas as pd
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="APK ABSENSI V1", layout="wide")
st.title("📍 APK ABSENSI KARYAWAN V1.6")

PASSWORD_ADMIN = "admin123"

@st.cache_resource
def connect_gsheet():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(creds)
    sh = client.open("REKAP")
    ws_absen = sh.worksheet("REKAP ABSENSI")
    ws_db = sh.worksheet("DATABASE KARYAWAN")
    ws_db.format('A:A', {'numberFormat': {'type': 'TEXT'}})
    ws_absen.format('A:A', {'numberFormat': {'type': 'TEXT'}})
    ws_absen.format('C:D', {'numberFormat': {'type': 'DATE_TIME', 'pattern': 'dd/mm/yyyy hh:mm:ss'}})
    return ws_absen, ws_db

ws_absen, ws_db = connect_gsheet()

@st.cache_data(ttl=60)
def load_data():
    db = pd.DataFrame(ws_db.get_all_records())
    db['ID KARYAWAN'] = db['ID KARYAWAN'].astype(str).str.zfill(8)
    absen = pd.DataFrame(ws_absen.get_all_records())
    if not absen.empty:
        absen['ID KARYAWAN'] = absen['ID KARYAWAN'].astype(str).str.zfill(8)
    else:
        absen = pd.DataFrame(columns=["ID KARYAWAN", "NAMA KARYAWAN", "JAM MASUK", "JAM PULANG", "JAM KERJA", "JAM LEMBUR", "SHIFT", "KETERANGAN"])
    return db, absen

db_df, absen_df = load_data()
st.success(f"✅ Konek. Karyawan: {len(db_df)} | Data Absen: {len(absen_df)}")

@st.cache_data(ttl=86400)
def get_libur(tahun):
    try:
        res = requests.get(f"https://indonesia-holiday-api.vercel.app/api/{tahun}", timeout=5)
        return {i['holiday_date']: i['holiday_name'] for i in res.json()}
    except: return {}

def hitung(masuk_str, pulang_str, status, libur_dict):
    if not masuk_str or not pulang_str: return "0:00:00", "0.00", "", ""
    masuk = datetime.strptime(masuk_str, '%d/%m/%Y %H:%M:%S')
    pulang = datetime.strptime(pulang_str, '%d/%m/%Y %H:%M:%S')
    total_jam_mentah = (pulang - masuk).total_seconds() / 3600

    # ATURAN: 8 JAM KERJA - 1 JAM ISTIRAHAT = 7 JAM EFEKTIF
    potong_istirahat = 1.0 if total_jam_mentah >= 8 else 0.0
    jam_kerja_float = total_jam_mentah - potong_istirahat
    if jam_kerja_float < 0: jam_kerja_float = 0

    tgl = masuk.strftime('%Y-%m-%d')
    weekday = masuk.weekday()
    is_libur = status in ["LIBUR", "TUKAR HARI"] or tgl in libur_dict or weekday == 6

    keterangan = "HARI KERJA"
    if status == "TUKAR HARI": keterangan = "TUKAR HARI"
    elif status == "LIBUR": keterangan = "LIBUR"
    elif tgl in libur_dict: keterangan = f"LIBUR NASIONAL: {libur_dict[tgl]}"
    elif weekday == 6: keterangan = "LIBUR MINGGU"
    elif weekday == 5: keterangan = "SABTU"

    # HITUNG LEMBUR - INI YG DIBENERIN
    lembur_x = 0.0
    if is_libur: # MINGGU/LIBUR NASIONAL
        lembur_x = jam_kerja_float * 2.0
        jam_kerja_float = 0 # semua masuk lembur
    elif weekday == 5: # SABTU
        jam_efektif_sabtu = 5.0
        if jam_kerja_float > jam_efektif_sabtu:
            lembur_jam = jam_kerja_float - jam_efektif_sabtu
            jam_pertama = min(1.0, lembur_jam)
            sisa = lembur_jam - jam_pertama
            lembur_x = (jam_pertama * 1.5) + (sisa * 2.0)
            jam_kerja_float = jam_efektif_sabtu
    else: # HARI KERJA SENIN-JUMAT
        jam_efektif_normal = 7.0
        if jam_kerja_float > jam_efektif_normal: # baru lembur kalau > 7 jam
            lembur_jam = jam_kerja_float - jam_efektif_normal
            jam_pertama = min(1.0, lembur_jam)
            sisa = lembur_jam - jam_pertama
            lembur_x = (jam_pertama * 1.5) + (sisa * 2.0)
            jam_kerja_float = jam_efektif_normal

    # SHIFT
    jam_masuk = masuk.hour
    jam_pulang = pulang.hour
    total_jam_efektif = jam_kerja_float + potong_istirahat
    if 7 <= jam_masuk < 8 and total_jam_efektif >= 10: shift = "LONG SHIFT1"
    elif 19 <= jam_masuk < 20 and total_jam_efektif >= 10: shift = "LONG SHIFT2"
    elif 900 <= jam_pulang*60 < 1380: shift = "SHIFT 1"
    else: shift = "SHIFT 2"

    return f"{int(jam_kerja_float)}:00:00", f"{lembur_x:.2f}", shift, keterangan

def upsert_absen(id_kar, masuk_dt, pulang_dt, nama):
    id_kar = id_kar.zfill(8)
    tgl_str = masuk_dt.strftime('%d/%m/%Y')
    libur_dict = get_libur(masuk_dt.year)
    jam_kerja, jam_lembur, shift, ket = hitung(masuk_dt.strftime('%d/%m/%Y %H:%M:%S'), pulang_dt.strftime('%d/%m/%Y %H:%M:%S'), "NORMAL", libur_dict)
    row_data = [id_kar, nama, masuk_dt.strftime('%d/%m/%Y %H:%M:%S'), pulang_dt.strftime('%d/%m/%Y %H:%M:%S'), jam_kerja, jam_lembur, shift, ket]
    existing = absen_df[(absen_df['ID KARYAWAN'] == id_kar) & (pd.to_datetime(absen_df['JAM MASUK'], errors='coerce').dt.strftime('%d/%m/%Y') == tgl_str)]
    if not existing.empty:
        row_num = existing.index[0] + 2
        ws_absen.update(f'A{row_num}:H{row_num}', [row_data])
    else:
        ws_absen.insert_row(row_data, 2)
    load_data.clear()

def auto_alpa_libur():
    libur_dict = get_libur(datetime.now().year)
    new_rows = []
    for i in range(1, 8):
        tgl = datetime.now() - timedelta(days=i)
        tgl_str = tgl.strftime('%d/%m/%Y')
        tgl_api = tgl.strftime('%Y-%m-%d')
        is_libur = tgl_api in libur_dict or tgl.weekday() == 6
        jam_auto = "00:00:00" if is_libur else "23:59:00"
        ket = f"LIBUR NASIONAL: {libur_dict[tgl_api]}" if tgl_api in libur_dict else ("LIBUR MINGGU" if tgl.weekday()==6 else "ALPA")
        shift = "LIBUR" if is_libur else "ALPA"
        for _, kar in db_df.iterrows():
            id_kar = kar['ID KARYAWAN']
            nama = kar['NAMA KARYAWAN']
            if absen_df[(absen_df['ID KARYAWAN']==id_kar) & (pd.to_datetime(absen_df['JAM MASUK'], errors='coerce').dt.strftime('%d/%m/%Y')==tgl_str)].empty:
                new_rows.append([id_kar, nama, f"{tgl_str} {jam_auto}", f"{tgl_str} {jam_auto}", "0:00:00", "0.00", shift, ket])
    if new_rows:
        ws_absen.insert_rows(new_rows, 2)
        load_data.clear()

menu = st.tabs(["📝 ABSEN", "✏️ EDIT DATA", "⚙️ ADMIN"])

with menu[0]:
    id_in = st.text_input("Masukkan ID Karyawan").strip().zfill(8)
    nama = ""
    if id_in:
        if id_in in db_df['ID KARYAWAN'].values:
            nama = db_df[db_df['ID KARYAWAN']==id_in]['NAMA KARYAWAN'].values[0]
            st.info(f"Nama: {nama}")
        else:
            st.error(f"ID {id_in} tidak ada di DATABASE KARYAWAN")

    col1, col2 = st.columns(2)
    with col1: tgl_masuk = st.date_input("Tgl Masuk", datetime.now())
    with col2: jam_masuk = st.time_input("Jam Masuk", datetime.now().time())
    col3, col4 = st.columns(2)
    with col3: tgl_pulang = st.date_input("Tgl Pulang", datetime.now())
    with col4: jam_pulang = st.time_input("Jam Pulang", datetime.now().time())

    if st.button("SIMPAN ABSEN", use_container_width=True):
        if nama:
            masuk_dt = datetime.combine(tgl_masuk, jam_masuk)
            pulang_dt = datetime.combine(tgl_pulang, jam_pulang)
            upsert_absen(id_in, masuk_dt, pulang_dt, nama)
            st.success("✅ Data tersimpan")
            st.rerun()
        else: st.warning("Isi ID yg benar dulu")

with menu[1]:
    if "login" not in st.session_state: st.session_state.login = False
    if not st.session_state.login:
        pw = st.text_input("Password Admin", type="password")
        if st.button("LOGIN"):
            if pw == PASSWORD_ADMIN: st.session_state.login = True; st.rerun()
            else: st.error("Salah")
    else:
        if st.button("LOGOUT"): st.session_state.login = False; st.rerun()
        id_edit = st.text_input("ID yg mau diedit").strip().zfill(8)
        if id_edit in db_df['ID KARYAWAN'].values:
            data_kar = absen_df[absen_df['ID KARYAWAN']==id_edit]
            if not data_kar.empty:
                pilih = st.selectbox("Pilih Tanggal", data_kar['JAM MASUK'].tolist())
                row = data_kar[data_kar['JAM MASUK']==pilih].iloc[0]
                new_masuk_tgl = st.date_input("Tgl Masuk Baru", pd.to_datetime(row['JAM MASUK']))
                new_masuk_jam = st.time_input("Jam Masuk Baru", pd.to_datetime(row['JAM MASUK']).time())
                new_pulang_tgl = st.date_input("Tgl Pulang Baru", pd.to_datetime(row['JAM PULANG']))
                new_pulang_jam = st.time_input("Jam Pulang Baru", pd.to_datetime(row['JAM PULANG']).time())
                if st.button("SIMPAN EDIT"):
                    masuk_dt = datetime.combine(new_masuk_tgl, new_masuk_jam)
                    pulang_dt = datetime.combine(new_pulang_tgl, new_pulang_jam)
                    upsert_absen(id_edit, masuk_dt, pulang_dt, row['NAMA KARYAWAN'])
                    st.success("✅ Edit berhasil")
                    st.rerun()
            else: st.warning("Belum ada data absen untuk ID ini")

with menu[2]:
    if st.button("⛪ JALANKAN AUTO ALPA/LIBUR"):
        auto_alpa_libur()
        st.success("✅ Selesai cek 7 hari kebelakang")
    if not absen_df.empty:
        st.dataframe(absen_df.sort_values('JAM MASUK', ascending=False), use_container_width=True)
    else:
        st.info("Belum ada data absen")
