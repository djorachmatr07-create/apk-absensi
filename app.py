import streamlit as st
import gspread
import requests
import pandas as pd
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="APK ABSENSI V1", layout="wide")
st.title("📍 APK ABSENSI KARYAWAN V3.4")

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
    ws_db.format('A:A', {'numberFormat': {'type': 'TEXT'}})
    ws_absen.format('A:A', {'numberFormat': {'type': 'TEXT'}})
    ws_absen.format('C:D', {'numberFormat': {'type': 'DATE_TIME', 'pattern': 'dd/mm/yyyy hh:mm:ss'}})
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

LIBUR_DICT = get_libur(datetime.now().year)

def buletin_jam(dt):
    return dt.replace(minute=0, second=0)

def get_shift_info(masuk_dt, is_sabtu=False):
    jam = masuk_dt.hour
    if is_sabtu:
        if 7 <= jam < 12: return "SHIFT 1 SABTU", masuk_dt.replace(hour=12, minute=0, second=0)
        elif 12 <= jam < 17: return "SHIFT 2 SABTU", masuk_dt.replace(hour=17, minute=0, second=0)
        else: return "SHIFT 3 SABTU", masuk_dt.replace(hour=23, minute=0, second=0)
    else:
        if 7 <= jam < 15: return "SHIFT 1", masuk_dt.replace(hour=15, minute=0, second=0)
        elif 15 <= jam < 23: return "SHIFT 2", masuk_dt.replace(hour=23, minute=0, second=0)
        else:
            efektif_pulang = masuk_dt.replace(hour=7, minute=0, second=0)
            if jam >= 23: efektif_pulang += timedelta(days=1)
            return "SHIFT 3", efektif_pulang

def hitung_lembur_normal(lembur_jam):
    if lembur_jam <= 0: return 0.0
    jam_pertama = min(1.0, lembur_jam)
    sisa = lembur_jam - jam_pertama
    return (jam_pertama * 1.5) + (sisa * 2.0)

def hitung(masuk_dt, pulang_dt, status):
    if not masuk_dt or not pulang_dt: return "0:00:00", "0.00", "", ""

    if status in ["A","I","S","C","L"]: return "0:00:00", "0.00", status, status
    if status == "SH": return "4:00:00", "0.00", "SETENGAH HARI", "SETENGAH HARI"
    if status == "DL": return "8:00:00", "0.00", "DINAS LUAR", "DINAS LUAR"
    if status == "WFH": return "8:00:00", "0.00", "WFH", "WORK FROM HOME"

    pulang_bulet = buletin_jam(pulang_dt)
    total_jam_mentah = (pulang_bulet - masuk_dt).total_seconds() / 3600

    tgl = masuk_dt.strftime('%Y-%m-%d')
    weekday = masuk_dt.weekday()
    is_tgl_merah = tgl in LIBUR_DICT
    is_minggu = weekday == 6
    is_sabtu = weekday == 5
    is_tukar_hari_biasa = status == "GH"
    is_tukar_hari_sabtu = status == "GHS"
    is_libur = (is_tgl_merah or is_minggu) and not is_tukar_hari_biasa and not is_tukar_hari_sabtu

    keterangan = "HARI KERJA"
    if is_tukar_hari_biasa: keterangan = "GANTI HARI BIASA"
    elif is_tukar_hari_sabtu: keterangan = "GANTI HARI SABTU"
    elif is_tgl_merah: keterangan = f"LIBUR NASIONAL: {LIBUR_DICT[tgl]}"
    elif is_minggu: keterangan = "LIBUR MINGGU"
    elif is_sabtu: keterangan = "SABTU"

    shift, jam_efektif_pulang = get_shift_info(masuk_dt, is_sabtu)
    lembur_x = 0.0
    jam_kerja_float = total_jam_mentah - (1.0 if total_jam_mentah >= 8 else 0.0)
    if jam_kerja_float < 0: jam_kerja_float = 0
    jam_kerja_final = jam_kerja_float

    if is_libur:
        jam_kerja_final = min(jam_kerja_float, 7.0)
        lembur_x = jam_kerja_final * 2.0
        batas_lembur = jam_efektif_pulang + timedelta(minutes=60)
        if pulang_bulet > batas_lembur:
            lembur_tambahan = (pulang_bulet - batas_lembur).total_seconds() / 3600
            lembur_x += lembur_tambahan * 2.0
    elif is_sabtu:
        jam_efektif = 5.0
        jam_kerja_final = min(jam_kerja_float, jam_efektif)
        if jam_kerja_float > jam_efektif:
            lembur_jam = jam_kerja_float - jam_efektif
            lembur_x = hitung_lembur_normal(lembur_jam)
    elif is_tukar_hari_sabtu:
        jam_efektif = 5.0
        jam_kerja_final = min(jam_kerja_float, jam_efektif)
        if jam_kerja_float > jam_efektif:
            lembur_jam = jam_kerja_float - jam_efektif
            lembur_x = hitung_lembur_normal(lembur_jam)
    else:
        jam_efektif = 7.0
        jam_kerja_final = min(jam_kerja_float, jam_efektif)
        batas_lembur = jam_efektif_pulang + timedelta(minutes=60)
        if pulang_bulet > batas_lembur:
            lembur_jam = (pulang_bulet - batas_lembur).total_seconds() / 3600
            lembur_x = hitung_lembur_normal(lembur_jam)

    if total_jam_mentah >= 10: shift = shift.replace("SHIFT", "LONG SHIFT")
    return f"{int(jam_kerja_final)}:00:00", f"{lembur_x:.2f}", shift, keterangan

def upsert_absen(id_kar, masuk_dt, pulang_dt, nama, status="H"):
    id_kar = id_kar.zfill(8)
    tgl_str = masuk_dt.strftime('%d/%m/%Y')
    jam_kerja, jam_lembur, shift, ket = hitung(masuk_dt, pulang_dt, status)
    row_data = [id_kar, nama, masuk_dt.strftime('%d/%m/%Y %H:%M:%S'), pulang_dt.strftime('%d/%m/%Y %H:%M:%S'), jam_kerja, jam_lembur, shift, ket]
    existing = absen_df[(absen_df['ID KARYAWAN'] == id_kar) & (absen_df['JAM MASUK DT'].dt.strftime('%d/%m/%Y') == tgl_str)]
    if not existing.empty:
        row_num = existing.index[0] + 2
        ws_absen.update(f'A{row_num}:H{row_num}', [row_data])
    else:
        ws_absen.insert_row(row_data, 2)
    load_data.clear() # CUKUP INI AJA, HAPUS GLOBAL

def rekalkulasi_semua():
    progress = st.progress(0)
    total = len(absen_df)
    for i, row in absen_df.iterrows():
        if pd.notna(row['JAM MASUK DT']) and row['KETERANGAN'] not in ['ALPA', 'LIBUR']:
            try:
                masuk_dt = pd.to_datetime(row['JAM MASUK'])
                pulang_dt = pd.to_datetime(row['JAM PULANG'])
                jam_kerja, jam_lembur, shift, ket = hitung(masuk_dt, pulang_dt, "H")
                row_num = i + 2
                ws_absen.update(f'E{row_num}:H{row_num}', [[jam_kerja, jam_lembur, shift, ket]])
            except: pass
        progress.progress((i + 1) / total)
    load_data.clear()

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
                kode_pilih = st.selectbox("Kode Status", options=list(MASTER_KODE.keys()), format_func=lambda x: f"{x} - {MASTER_KODE[x]['nama']}")
                st.info(f"**{MASTER_KODE[kode_pilih]['nama']}** | Gaji: {MASTER_KODE[kode_pilih]['gaji']} | Jam: {MASTER_KODE[kode_pilih]['jam']}")
                col1, col2 = st.columns(2)
                with col1: new_masuk_tgl = st.date_input("Tgl Masuk Baru", pd.to_datetime(row['JAM MASUK']))
                with col2: new_masuk_jam = st.time_input("Jam Masuk Baru", pd.to_datetime(row['JAM MASUK']).time())
                col3, col4 = st.columns(2)
                with col3: new_pulang_tgl = st.date_input("Tgl Pulang Baru", pd.to_datetime(row['JAM PULANG']))
                with col4: new_pulang_jam = st.time_input("Jam Pulang Baru", pd.to_datetime(row['JAM PULANG']).time())
                if st.button("SIMPAN EDIT"):
                    masuk_dt = datetime.combine(new_masuk_tgl, new_masuk_jam)
                    pulang_dt = datetime.combine(new_pulang_tgl, new_pulang_jam)
                    with st.spinner("Menyimpan 1-3 detik..."):
                        upsert_absen(id_edit, masuk_dt, pulang_dt, row['NAMA KARYAWAN'], kode_pilih)
                    st.success(f"✅ Edit berhasil. Status: {MASTER_KODE[kode_pilih]['nama']}")

with menu[2]:
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 REKALKULASI SEMUA DATA", use_container_width=True, type="primary"):
            with st.spinner("Sedang menghitung ulang..."):
                rekalkulasi_semua()
            st.success("✅ Selesai! Semua data keupdate")
            st.rerun()
    with col2:
        if st.button("🗑️ REFRESH DATA", use_container_width=True):
            load_data.clear()
            st.rerun()

    if not absen_df.empty:
        st.dataframe(absen_df.sort_values('JAM MASUK DT', ascending=True), use_container_width=True)
