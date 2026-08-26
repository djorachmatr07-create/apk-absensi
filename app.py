import streamlit as st
import gspread
import requests
import pandas as pd
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="APK ABSENSI V1", layout="wide")
st.title("📍 APK ABSENSI KARYAWAN V4.7")

PASSWORD_ADMIN = "admin123"

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
        if 'STATUS' not in absen.columns: absen['STATUS'] = 'H'
    else:
        absen = pd.DataFrame(columns=["ID KARYAWAN", "NAMA KARYAWAN", "JAM MASUK", "JAM PULANG", "JAM KERJA", "JAM LEMBUR", "SHIFT", "KETERANGAN", "STATUS", "JAM MASUK DT"])
    return db, absen

db_df, absen_df = load_data()
st.success(f"✅ Konek. Karyawan: {len(db_df)} | Data Absen: {len(absen_df)}")

# === FUNGSI BACA KALENDER INDONESIA ===
@st.cache_data(ttl=86400) # Cache 1 hari
def get_libur_nasional():
    libur = {}
    tahun_sekarang = datetime.now().year
    for tahun in [tahun_sekarang - 1, tahun_sekarang, tahun_sekarang + 1]: # Ambil 3 tahun biar aman
        try:
            url = f"https://dayoffapi.vercel.app/api/{tahun}" # API Kalender Indonesia yg lebih lengkap
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                for item in res.json():
                    tgl = item['tanggal'] # format: 2026-08-17
                    libur[tgl] = item['keterangan']
        except:
            st.warning(f"Gagal ambil data libur tahun {tahun}")
    return libur

LIBUR_NASIONAL = get_libur_nasional()
st.info(f"✅ Data Kalender Nasional Loaded: {len(LIBUR_NASIONAL)} hari libur")

def cek_keterangan_libur(tanggal_dt, status):
    """Fungsi inti buat baca kalender"""
    tgl_str = tanggal_dt.strftime('%Y-%m-%d')
    weekday = tanggal_dt.weekday() # 0=Senin... 6=Minggu

    if status!= "L":
        return "HARI KERJA" # Kalau bukan L, gak usah cek

    # URUTAN CEK: 1. Tgl Merah > 2. Minggu > 3. Libur biasa
    if tgl_str in LIBUR_NASIONAL:
        return f"LIBUR NASIONAL: {LIBUR_NASIONAL[tgl_str]}"
    elif weekday == 6:
        return "LIBUR MINGGU"
    else:
        return "LIBUR"

def hitung(masuk_dt, pulang_dt, status):
    tgl = masuk_dt.strftime('%Y-%m-%d')
    weekday = masuk_dt.weekday()
    is_sabtu = weekday == 5

    # DAPETIN KETERANGAN DARI FUNGSI BARU
    keterangan = cek_keterangan_libur(masuk_dt, status)

    if status == "L":
        shift = "L"
        jam_kerja = "0:00:00"
        jam_lembur = "0.00"
    elif status == "A": shift, jam_kerja, jam_lembur = "A", "0:00:00", "0.00"
    elif status == "I": shift, jam_kerja, jam_lembur = "I", "0:00:00", "0.00"
    elif status == "S": shift, jam_kerja, jam_lembur = "S", "0:00:00", "0.00"
    elif status == "C": shift, jam_kerja, jam_lembur = "C", "0:00:00", "0.00"
    elif status == "GH": shift, jam_kerja, jam_lembur = "SHIFT 2", "7:00:00", "0.00"
    elif status == "GHS": shift, jam_kerja, jam_lembur = "SHIFT 1 SABTU", "5:00:00", "0.00"
    else:
        shift = "SHIFT 2" if 15 <= masuk_dt.hour < 23 else "SHIFT 1"
        jam_kerja, jam_lembur = "7:00:00", "0.00"

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
        ws_absen.update(f'A{row_num}:I{row_num}', [row_data])
    else:
        ws_absen.insert_row(row_data, 2)
    load_data.clear()

def update_semua_keterangan_libur():
    if absen_df.empty: return 0
    data_l = absen_df[absen_df['STATUS'] == 'L'].copy()
    if data_l.empty: return 0

    updates = []
    for i, row in data_l.iterrows():
        masuk_dt = pd.to_datetime(row['JAM MASUK'])
        ket_baru = cek_keterangan_libur(masuk_dt, "L") # PAKE FUNGSI CEK KALENDER
        row_num = i + 2
        updates.append({'range': f'G{row_num}:H{row_num}', 'values': [['L', ket_baru]]})

    ws_absen.batch_update(updates)
    load_data.clear()
    return len(updates)

menu = st.tabs(["📝 ABSEN", "✏️ EDIT DATA", "⚙️ ADMIN"])

with menu[0]:
    id_in = st.text_input("Masukkan ID Karyawan").strip().zfill(8)
    nama = ""
    if id_in:
        if id_in in db_df['ID KARYAWAN'].values:
            nama = db_df[db_df['ID KARYAWAN']==id_in]['NAMA KARYAWAN'].values[0]
            st.info(f"Nama: {nama}")
        else: st.error(f"ID {id_in} tidak ada")

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
            with st.spinner("Menyimpan..."):
                upsert_absen(id_in, masuk_dt, pulang_dt, nama, "H")
            st.success("✅ Data tersimpan")

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
                pilih = st.selectbox("Pilih Tanggal", data_kar.sort_values('JAM MASUK DT')['JAM MASUK'].tolist())
                row = data_kar[data_kar['JAM MASUK']==pilih].iloc[0]
                kode_pilih = st.selectbox("Kode Status", options=["H","A","I","S","C","L","GH","GHS"])
                if st.button("SIMPAN EDIT"):
                    masuk_dt = pd.to_datetime(row['JAM MASUK'])
                    pulang_dt = pd.to_datetime(row['JAM PULANG'])
                    with st.spinner("Menyimpan..."):
                        upsert_absen(id_edit, masuk_dt, pulang_dt, row['NAMA KARYAWAN'], kode_pilih)
                    st.success(f"✅ Edit berhasil. Status: {kode_pilih}")

with menu[2]:
    if st.button("🔄 UPDATE KETERANGAN LIBUR DARI KALENDER", use_container_width=True, type="primary"):
        with st.spinner("Sedang baca kalender & update semua data L..."):
            jml = update_semua_keterangan_libur()
        st.success(f"✅ Selesai! {jml} data L diupdate dari Kalender Nasional")
        st.rerun()
    if st.button("🗑️ REFRESH DATA", use_container_width=True):
        load_data.clear()
        st.rerun()
    if not absen_df.empty:
        st.dataframe(absen_df.sort_values('JAM MASUK DT', ascending=False), use_container_width=True)
