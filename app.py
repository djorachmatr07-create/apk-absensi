import streamlit as st
import gspread
import pandas as pd
import requests 
from datetime import datetime
from google.oauth2.service_account import Credentials
from icalendar import Calendar 

st.set_page_config(page_title="APK ABSENSI V1", layout="wide")
st.title("📍 APK ABSENSI KARYAWAN V6.2 - AUTO LIBUR")

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
        st.success(f"✅ Ambil {len(libur)} hari libur dari Kalender RI")
        return libur
    except Exception as e:
        st.error(f"Gagal ambil ICS: {e}")
        return {}

LIBUR_NASIONAL = get_libur_dari_ics()

@st.cache_data(ttl=300)
def load_data():
    db = pd.DataFrame(ws_db.get_all_records())
    db['ID KARYAWAN'] = db['ID KARYAWAN'].astype(str).str.zfill(8)
    absen = pd.DataFrame(ws_absen.get_all_records())
    if 'STATUS' not in absen.columns:
        absen['STATUS'] = 'H'
        ws_absen.update('I1', [['STATUS']])
    if not absen.empty:
        absen['ID KARYAWAN'] = absen['ID KARYAWAN'].astype(str).str.zfill(8)
        absen['JAM MASUK DT'] = pd.to_datetime(absen['JAM MASUK'], format='%d/%m/%Y %H:%M:%S', errors='coerce')
    else:
        absen = pd.DataFrame(columns=["ID KARYAWAN", "NAMA KARYAWAN", "JAM MASUK", "JAM PULANG", "JAM KERJA", "JAM LEMBUR", "SHIFT", "KETERANGAN", "STATUS", "JAM MASUK DT"])
    return db, absen

db_df, absen_df = load_data()

def cek_keterangan_dari_tanggal(tanggal_dt, jam_masuk_str, jam_pulang_str, jam_kerja_float):
    tgl_str = tanggal_dt.strftime('%Y-%m-%d')
    weekday = tanggal_dt.weekday()
    if jam_masuk_str and jam_pulang_str and jam_masuk_str!= jam_pulang_str and jam_kerja_float > 0:
        return "MASUK"
    if jam_kerja_float == 0:
        if tgl_str in LIBUR_NASIONAL:
            return f"LIBUR NASIONAL: {LIBUR_NASIONAL[tgl_str]}"
        elif weekday == 6:
            return "LIBUR MINGGU"
        elif weekday == 5:
            return "SABTU"
        else:
            return "TIDAK MASUK"
    return "HARI KERJA"

def hitung(masuk_dt, pulang_dt, status):
    total_jam_mentah = (pulang_dt - masuk_dt).total_seconds() / 3600
    jam_kerja_float = total_jam_mentah - (1.0 if total_jam_mentah >= 8 else 0.0)
    if jam_kerja_float < 0: jam_kerja_float = 0
    jam_masuk_str = masuk_dt.strftime('%d/%m/%Y %H:%M:%S')
    jam_pulang_str = pulang_dt.strftime('%d/%m/%Y %H:%M:%S')
    keterangan = cek_keterangan_dari_tanggal(masuk_dt, jam_masuk_str, jam_pulang_str, jam_kerja_float)
    if keterangan == "MASUK":
        shift = "SHIFT 2" if 15 <= masuk_dt.hour < 23 else "SHIFT 1"
    elif jam_kerja_float == 0:
        shift = status if status in ['A','I','S','C','L'] else 'L'
    else:
        shift = "SHIFT 2" if 15 <= masuk_dt.hour < 23 else "SHIFT 1"
    return f"{int(jam_kerja_float)}:00:00", "0.00", shift, keterangan, jam_masuk_str, jam_pulang_str

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

def update_semua_keterangan():
    if absen_df.empty: return 0
    updates = []
    for i, row in absen_df.iterrows():
        masuk_dt = pd.to_datetime(row['JAM MASUK'])
        jam_kerja_str = row['JAM KERJA']
        jam_kerja_float = 0 if jam_kerja_str == '0:00:00' else float(jam_kerja_str.split(':')[0])
        ket_baru = cek_keterangan_dari_tanggal(masuk_dt, row['JAM MASUK'], row['JAM PULANG'], jam_kerja_float)
        status_lama = row.get('STATUS', 'H')
        if 'LIBUR' in ket_baru: shift_baru = 'L'
        elif status_lama in ['A','I','S','C']: shift_baru = status_lama
        else: shift_baru = 'H'
        row_num = i + 2
        updates.append({'range': f'G{row_num}:H{row_num}', 'values': [[shift_baru, ket_baru]]})
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
            upsert_absen(id_in, masuk_dt, pulang_dt, nama, "H")
            st.success("✅ Data tersimpan")
with menu[2]:
    if st.button("🔄 UPDATE SEMUA KETERANGAN DARI KALENDER", type="primary"):
        jml = update_semua_keterangan()
        st.success(f"✅ Selesai! {jml} data diupdate")
        st.rerun()
    if not absen_df.empty:
        st.dataframe(absen_df.sort_values('JAM MASUK DT', ascending=False), use_container_width=True)
