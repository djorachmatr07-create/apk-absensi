import streamlit as st
import gspread
import pandas as pd
import requests
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from icalendar import Calendar

st.set_page_config(page_title="APK ABSENSI V1", layout="wide")
st.title("📍 APK ABSENSI + GAJI KARYAWAN V7.3 - BULAT JAM")

PASSWORD_ADMIN = "admin123"
ICS_URL = "https://calendar.google.com/calendar/ical/id.indonesian%23holiday%40group.v.calendar.google.com/public/basic.ics"

@st.cache_resource
def connect_gsheet():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(creds)
    sh = client.open("REKAP")
    return sh.worksheet("REKAP ABSENSI"), sh.worksheet("DATABASE KARYAWAN")

ws_absen, ws_db = connect_gsheet()

@st.cache_data(ttl=86400)
def get_libur_dari_ics():
    try:
        r = requests.get(ICS_URL, timeout=10)
        cal = Calendar.from_ical(r.text)
        libur = {}
        for component in cal.walk():
            if component.name == "VEVENT":
                start = component.get('dtstart').dt
                if hasattr(start, 'strftime'):
                    start = start.strftime('%Y-%m-%d')
                libur[start] = str(component.get('summary'))
        return libur
    except: return {}

LIBUR_NASIONAL = get_libur_dari_ics()

@st.cache_data(ttl=300)
def load_data():
    db = pd.DataFrame(ws_db.get_all_records())
    db['ID KARYAWAN'] = db['ID KARYAWAN'].astype(str).str.zfill(8)
    absen = pd.DataFrame(ws_absen.get_all_records())
    for col in ['STATUS', 'JAM LEMBUR', 'JAM KERJA', 'SHIFT', 'KETERANGAN']:
        if col not in absen.columns: absen[col] = ''
    if not absen.empty:
        absen['ID KARYAWAN'] = absen['ID KARYAWAN'].astype(str).str.zfill(8)
        absen['JAM MASUK DT'] = pd.to_datetime(absen['JAM MASUK'], format='%d/%m/%Y %H:%M:%S', errors='coerce')
    else:
        absen = pd.DataFrame(columns=["ID KARYAWAN", "NAMA KARYAWAN", "JAM MASUK", "JAM PULANG", "JAM KERJA", "JAM LEMBUR", "SHIFT", "KETERANGAN", "STATUS", "JAM MASUK DT"])
    return db, absen

db_df, absen_df = load_data()

def bulatkan_ke_jam_pas(dt):
    # 06:30 ke atas -> naik 1 jam. 06:29 ke bawah -> turun
    if dt.minute >= 30:
        return dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else:
        return dt.replace(minute=0, second=0, microsecond=0)

def cek_keterangan_dari_tanggal(tanggal_dt, jam_masuk_str, jam_pulang_str, jam_kerja_float, status):
    tgl_str = tanggal_dt.strftime('%Y-%m-%d')
    weekday = tanggal_dt.weekday()
    if jam_masuk_str and jam_pulang_str and jam_masuk_str!= jam_pulang_str and jam_kerja_float > 0:
        if tgl_str in LIBUR_NASIONAL or weekday == 6: return "LEMBUR HARI LIBUR"
        else: return "MASUK"
    if jam_kerja_float == 0:
        if status == 'L' or tgl_str in LIBUR_NASIONAL: return f"LIBUR NASIONAL: {LIBUR_NASIONAL.get(tgl_str, 'LIBUR')}"
        elif status == 'A': return "ALFA"
        elif status == 'I': return "IZIN"
        elif status == 'S': return "SAKIT"
        elif status == 'C': return "CUTI"
        elif weekday == 6: return "LIBUR MINGGU"
        elif weekday == 5: return "SABTU"
        else: return "TIDAK MASUK"
    return "HARI KERJA"

def cek_shift(jam_masuk_dt, jam_kerja_float, keterangan, status):
    if 'LIBUR' in keterangan: return 'SL'
    if status == 'A': return 'A'
    if status == 'I': return 'I'
    if status == 'S': return 'S'
    if status == 'C': return 'C'
    if jam_kerja_float == 0: return '-'
    if jam_kerja_float >= 11.5: return 'LS' # LONGSHIFT
    jam = jam_masuk_dt.hour
    if 7 <= jam < 15: return 'S1'
    elif 15 <= jam < 23: return 'S2'
    else: return 'S3' # 23-07

def hitung_lembur(jam_kerja_float, keterangan):
    jam_normal = 8.0
    jam_lembur = 0.0
    if 'LEMBUR' in keterangan: jam_lembur = jam_kerja_float
    elif jam_kerja_float > jam_normal: jam_lembur = jam_kerja_float - jam_normal
    return f"{jam_lembur:.2f}"

def hitung(masuk_dt, pulang_dt, status):
    # 1. BULATKAN JAM DULU KE JAM PAS
    masuk_dt = bulatkan_ke_jam_pas(masuk_dt)
    pulang_dt = bulatkan_ke_jam_pas(pulang_dt)

    total_jam_mentah = (pulang_dt - masuk_dt).total_seconds() / 3600

    # 2. POTONG ISTIRAHAT 1 JAM KALAU KERJA >= 8 JAM
    if total_jam_mentah >= 8.0: jam_kerja_float = total_jam_mentah - 1.0
    else: jam_kerja_float = total_jam_mentah
    if jam_kerja_float < 0: jam_kerja_float = 0

    jam_masuk_str = masuk_dt.strftime('%d/%m/%Y %H:%M:%S')
    jam_pulang_str = pulang_dt.strftime('%d/%m/%Y %H:%M:%S')
    keterangan = cek_keterangan_dari_tanggal(masuk_dt, jam_masuk_str, jam_pulang_str, jam_kerja_float, status)
    shift = cek_shift(masuk_dt, jam_kerja_float, keterangan, status)
    jam_lembur = hitung_lembur(jam_kerja_float, keterangan)

    # 3. KODE GAJI
    if 'LEMBUR HARI LIBUR' in keterangan: keterangan = 'OTMING'
    elif float(jam_lembur) > 0: keterangan = 'OTWD'
    elif shift == 'LS': keterangan = 'LONGSHIFT'
    elif shift == 'SL': keterangan = 'SHIFT LIBUR'
    elif shift in ['S1','S2','S3']: keterangan = 'MASUK'

    return f"{jam_kerja_float:.2f}", jam_lembur, shift, keterangan, jam_masuk_str, jam_pulang_str

def upsert_absen(id_kar, masuk_dt, pulang_dt, nama, status="H"):
    id_kar = id_kar.zfill(8)
    tgl_str = masuk_dt.strftime('%d/%m/%Y')
    jam_kerja, jam_lembur, shift, ket, jam_masuk_str, jam_pulang_str = hitung(masuk_dt, pulang_dt, status)
    row_data = [id_kar, nama, jam_masuk_str, jam_pulang_str, jam_kerja, jam_lembur, shift, ket, status]
    if not absen_df.empty:
        existing = absen_df[(absen_df['ID KARYAWAN'] == id_kar) & (absen_df['JAM MASUK DT'].dt.strftime('%d/%m/%Y') == tgl_str)]
    else: existing = pd.DataFrame()
    if not existing.empty:
        row_num = existing.index[0] + 2
        ws_absen.update(f'A{row_num}:I{row_num}', [row_data])
    else: ws_absen.insert_row(row_data, 2)
    load_data.clear()

def update_semua_keterangan():
    if absen_df.empty: return 0
    updates = []
    for i, row in absen_df.iterrows():
        masuk_dt = pd.to_datetime(row['JAM MASUK'])
        pulang_dt = pd.to_datetime(row['JAM PULANG'])
        status_lama = row.get('STATUS', 'H')
        jam_kerja, jam_lembur, shift, ket, _, _ = hitung(masuk_dt, pulang_dt, status_lama)
        row_num = i + 2
        updates.append({'range': f'E{row_num}:I{row_num}', 'values': [[jam_kerja, jam_lembur, shift, ket, status_lama]]})
    ws_absen.batch_update(updates)
    load_data.clear()
    return len(updates)

menu = st.tabs(["📝 ABSEN", "✏️ EDIT DATA", "⚙️ ADMIN", "📊 REKAP"])
with menu[0]:
    id_in = st.text_input("Masukkan ID Karyawan").strip().zfill(8)
    nama = ""
    if id_in:
        if id_in in db_df['ID KARYAWAN'].values: nama = db_df[db_df['ID KARYAWAN']==id_in]['NAMA KARYAWAN'].values[0]; st.info(f"Nama: {nama}")
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
            upsert_absen(id_in, masuk_dt, pulang_dt, nama, "H")
            st.success("✅ Data tersimpan & sudah dibulatkan")

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
                kode_pilih = st.selectbox("Kode Status", options=["H","A","I","S","C","L"])
                if st.button("SIMPAN EDIT"):
                    masuk_dt = pd.to_datetime(row['JAM MASUK'])
                    pulang_dt = pd.to_datetime(row['JAM PULANG'])
                    upsert_absen(id_edit, masuk_dt, pulang_dt, row['NAMA KARYAWAN'], kode_pilih)
                    st.success(f"✅ Edit berhasil. Status: {kode_pilih}")

with menu[2]:
    if st.button("🔄 UPDATE SEMUA KETERANGAN DARI KALENDER", type="primary"):
        jml = update_semua_keterangan()
        st.success(f"✅ Selesai! {jml} data diupdate & dibulatkan")
        st.rerun()

with menu[3]:
    st.dataframe(absen_df.sort_values('JAM MASUK DT', ascending=False), use_container_width=True)
