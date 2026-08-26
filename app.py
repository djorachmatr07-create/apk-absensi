import streamlit as st
import gspread
import pandas as pd
import requests
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from icalendar import Calendar

st.set_page_config(page_title="APK ABSENSI V1", layout="wide")
st.title("📍 APK ABSENSI V9.0 - FIX ERROR HEADER")

st.markdown("""<style>div.stButton > button[kind="primary"][data-testid="baseButton-secondary"] {background-color: #DC2626; color: white; border: none;} </style>""", unsafe_allow_html=True)

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
                if hasattr(start, 'strftime'): start = start.strftime('%Y-%m-%d')
                libur[start] = str(component.get('summary'))
        return libur
    except: return {}

LIBUR_NASIONAL = get_libur_dari_ics()

@st.cache_data(ttl=300)
def load_data():
    db = pd.DataFrame(ws_db.get_all_records())
    db['ID KARYAWAN'] = db['ID KARYAWAN'].astype(str).str.zfill(8)
    
    # BACA PAKAI VALUES BIAR GAK ERROR HEADER
    all_values = ws_absen.get_all_values()
    if len(all_values) > 1:
        header = ['ID KARYAWAN', 'NAMA KARYAWAN', 'JAM MASUK', 'JAM PULANG', 'JAM KERJA', 'JAM LEMBUR', 'SHIFT', 'KETERANGAN', 'STATUS']
        absen = pd.DataFrame(all_values[1:], columns=header)
    else:
        absen = pd.DataFrame(columns=header)

    if not absen.empty:
        absen['ID KARYAWAN'] = absen['ID KARYAWAN'].astype(str).str.zfill(8)
        absen['JAM MASUK DT'] = pd.to_datetime(absen['JAM MASUK'], format='%d/%m/%Y %H:%M:%S', errors='coerce')
        absen['TGL'] = absen['JAM MASUK DT'].dt.strftime('%d/%m/%Y')
        absen[['LEMBUR 1.5', 'LEMBUR 2.0']] = absen.apply(lambda x: pd.Series(hitung_lembur_baru(float(x['JAM KERJA'] or 0))), axis=1)
    else:
        absen['JAM MASUK DT'] = pd.to_datetime([])
        absen['TGL'] = []
        absen['LEMBUR 1.5'] = []
        absen['LEMBUR 2.0'] = []
    return db, absen

db_df, absen_df = load_data()

def bulatkan_ke_jam_pas(dt):
    if dt.minute >= 30: return dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else: return dt.replace(minute=0, second=0, microsecond=0)

def cek_keterangan_dari_tanggal(tanggal_dt, jam_masuk_str, jam_pulang_str, jam_kerja_float, status):
    tgl_str = tanggal_dt.strftime('%Y-%m-%d')
    weekday = tanggal_dt.weekday()
    if jam_masuk_str and jam_pulang_str and jam_masuk_str!= jam_pulang_str and jam_kerja_float > 0: return "MASUK"
    if jam_kerja_float == 0:
        if status == 'L' or tgl_str in LIBUR_NASIONAL:
            if tgl_str in LIBUR_NASIONAL: return f"LIBUR NASIONAL: {LIBUR_NASIONAL[tgl_str]}"
            else: return "SHIFT LIBUR"
        elif status == 'A': return "ALFA"
        elif status == 'I': return "IZIN"
        elif status == 'S': return "SAKIT"
        elif status == 'C': return "CUTI"
        elif status == 'TL': return "TUKAR LIBUR"
        elif status == 'GH': return "GANTI HARI"
        elif status == 'GHS': return "GANTI HARI SABTU"
        elif weekday == 6: return "LIBUR MINGGU"
        elif weekday == 5: return "SABTU"
        else: return "TIDAK MASUK"
    return "HARI KERJA"

def cek_shift(jam_masuk_dt, jam_pulang_dt, jam_kerja_float, keterangan, status):
    if 'LIBUR' in keterangan: return 'SL'
    if status in ['A','I','S','C','TL']: return status
    if jam_kerja_float == 0: return '-'
    jam_masuk = jam_masuk_dt.hour
    if jam_masuk >= 19: return f"{status}-LS2"
    if jam_kerja_float >= 11.5: shift_code = 'LS1'
    else:
        if 7 <= jam_masuk < 15: shift_code = 'S1'
        elif 15 <= jam_masuk < 23: shift_code = 'S2'
        else: shift_code = 'S3'
    if keterangan == "MASUK": return f"{status}-{shift_code}"
    else: return shift_code

def hitung_lembur_baru(jam_kerja_float):
    jam_normal = 7.0
    lembur_1_5 = 0.0
    lembur_2_0 = 0.0
    if jam_kerja_float > jam_normal:
        jam_lembur_total = jam_kerja_float - jam_normal
        if jam_lembur_total >= 1.0:
            lembur_1_5 = 1.0
            if jam_lembur_total > 1.0:
                lembur_2_0 = jam_lembur_total - 1.0
    return f"{lembur_1_5:.2f}", f"{lembur_2_0:.2f}"

def hitung(masuk_dt, pulang_dt, status):
    masuk_dt = bulatkan_ke_jam_pas(masuk_dt)
    pulang_dt = bulatkan_ke_jam_pas(pulang_dt)
    total_jam_mentah = (pulang_dt - masuk_dt).total_seconds() / 3600
    if total_jam_mentah >= 8.0: jam_kerja_float = total_jam_mentah - 1.0
    else: jam_kerja_float = total_jam_mentah
    if jam_kerja_float < 0: jam_kerja_float = 0
    jam_masuk_str = masuk_dt.strftime('%d/%m/%Y %H:%M:%S')
    jam_pulang_str = pulang_dt.strftime('%d/%m/%Y %H:%M:%S')
    keterangan = cek_keterangan_dari_tanggal(masuk_dt, jam_masuk_str, jam_pulang_str, jam_kerja_float, status)
    shift = cek_shift(masuk_dt, pulang_dt, jam_kerja_float, keterangan, status)
    lembur_1_5, lembur_2_0 = hitung_lembur_baru(jam_kerja_float)
    jam_lembur_total = float(lembur_1_5) + float(lembur_2_0)
    return f"{jam_kerja_float:.2f}", f"{jam_lembur_total:.2f}", shift, keterangan, jam_masuk_str, jam_pulang_str

def upsert_absen(id_kar, masuk_dt, pulang_dt, nama, status="H", sudah_pulang=False):
    id_kar = id_kar.zfill(8)
    tgl_str = masuk_dt.strftime('%d/%m/%Y') if masuk_dt else datetime.now().strftime('%d/%m/%Y')
    STATUS_NON_JAM = ['A','I','S','C','L','GH','GHS','TL']
    if status in STATUS_NON_JAM:
        jam_masuk_str = ""
        jam_pulang_str = ""
        jam_kerja = "0.00"
        jam_lembur = "0.00"
        shift = status
        ket = cek_keterangan_dari_tanggal(datetime.now(), "", "", 0, status)
    elif not sudah_pulang:
        jam_masuk_str = masuk_dt.strftime('%d/%m/%Y %H:%M:%S')
        jam_pulang_str = ""
        jam_kerja = "0.00"
        jam_lembur = "0.00"
        shift = "-"
        ket = "BELUM ABSEN PULANG"
    else:
        jam_kerja, jam_lembur, shift, ket, jam_masuk_str, jam_pulang_str = hitung(masuk_dt, pulang_dt, status)
    row_data = [id_kar, nama, jam_masuk_str, jam_pulang_str, jam_kerja, jam_lembur, shift, ket, status]
    existing = absen_df[(absen_df['ID KARYAWAN'] == id_kar) & (absen_df['TGL'] == tgl_str)]
    if not existing.empty:
        row_num = existing.index[0] + 2
        ws_absen.update(f'A{row_num}:I{row_num}', [row_data])
    else:
        ws_absen.append_row(row_data)
    load_data.clear()

def update_semua_keterangan():
    if absen_df.empty: return 0
    updates = []
    for i, row in absen_df.iterrows():
        masuk_dt = pd.to_datetime(row['JAM MASUK']) if row['JAM MASUK'] else datetime.now()
        pulang_dt = pd.to_datetime(row['JAM PULANG']) if row['JAM PULANG'] else datetime.now()
        status_lama = row.get('STATUS', 'H')
        jam_kerja, jam_lembur, shift, ket, _, _ = hitung(masuk_dt, pulang_dt, status_lama)
        row_num = i + 2
        updates.append({'range': f'E{row_num}:I{row_num}', 'values': [[jam_kerja, jam_lembur, shift, ket, status_lama]]})
    ws_absen.batch_update(updates)
    load_data.clear()
    return len(updates)

menu = st.tabs(["📝 ABSEN", "✏️ EDIT DATA", "⚙️ ADMIN", "📊 REKAP"])
#... SISA KODE TAB SAMA KAYAK V8.9...
