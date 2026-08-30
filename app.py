import streamlit as st
import gspread
import pandas as pd
import requests
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from icalendar import Calendar

st.set_page_config(page_title="APK ABSENSI V10.8.4 FINAL", layout="wide")
st.title("📍 APK ABSENSI V10.8.4 FINAL - MINGGU 7 JAM X2.0 | SABTU 5 JAM +1.5+2.0")

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
HEADER = ['ID KARYAWAN', 'NAMA KARYAWAN', 'TANGGAL', 'JAM MASUK', 'JAM PULANG', 'JAM KERJA', 'JAM LEMBUR', 'LEMBUR 1.5', 'LEMBUR 2.0', 'SHIFT', 'KETERANGAN', 'STATUS', 'UANG SHIFT']

# ================= RUMUS LENGKAP FINAL =================
def hitung_lembur_lengkap(jam_total_float, is_sabtu=False, is_minggu=False, is_tgl_merah=False):
    try: jam_total_float = float(jam_total_float or 0)
    except: jam_total_float = 0.0
    if jam_total_float <= 0:
        return "0.00", "0.00", "0.00", "0.00"

    # 1. MINGGU & TANGGAL MERAH: 7 JAM EFEKTIF X2.0
    if is_minggu or is_tgl_merah:
        if jam_total_float <= 7.0:
            # Kerja 7 jam di Minggu = 7 jam x2.0
            return "0.00", f"{jam_total_float:.2f}", "0.00", f"{jam_total_float:.2f}"
        else:
            # Lebih dari 7 jam, semua tetap x2.0
            return "0.00", f"{jam_total_float:.2f}", "0.00", f"{jam_total_float:.2f}"

    # 2. SABTU: 5 JAM EFEKTIF + 1 JAM X1.5 + SISANYA X2.0
    if is_sabtu:
        if jam_total_float <= 5.0:
            return f"{jam_total_float:.2f}", "0.00", "0.00", "0.00"
        sisa = jam_total_float - 5.0
        if sisa >= 1.0:
            l15 = 1.0
            l20 = sisa - 1.0
        else:
            l15 = sisa
            l20 = 0.0
        return "5.00", f"{(l15+l20):.2f}", f"{l15:.2f}", f"{l20:.2f}"

    # 3. SENIN-JUMAT: 7 JAM EFEKTIF + 1 JAM X1.5 + SISANYA X2.0
    if jam_total_float <= 7.0:
        return f"{jam_total_float:.2f}", "0.00", "0.00", "0.00"
    sisa = jam_total_float - 7.0
    if sisa >= 1.0:
        l15 = 1.0
        l20 = sisa - 1.0
    else:
        l15 = sisa
        l20 = 0.0
    return "7.00", f"{(l15+l20):.2f}", f"{l15:.2f}", f"{l20:.2f}"

@st.cache_data(ttl=60)
def load_data():
    db = pd.DataFrame(ws_db.get_all_records())
    db['ID KARYAWAN'] = db['ID KARYAWAN'].astype(str).str.zfill(8)
    col_uang = None
    for c in db.columns:
        if 'SHIFT' in c.upper() and 'UANG' in c.upper(): col_uang = c
    if not col_uang:
        for c in ['UANG SHIFT','UANG_SHIFT','TUNJANGAN SHIFT','SHIFT','UANG']:
            if c in db.columns: col_uang = c; break
    if not col_uang: col_uang = db.columns[-1]
    all_values = ws_absen.get_all_values()
    if len(all_values) > 1:
        data = [row[:13] for row in all_values[1:]]
        absen = pd.DataFrame(data, columns=HEADER) if data else pd.DataFrame(columns=HEADER)
    else: absen = pd.DataFrame(columns=HEADER)
    if not absen.empty:
        absen['ID KARYAWAN'] = absen['ID KARYAWAN'].astype(str).str.zfill(8)
        absen['TGL_DT'] = pd.to_datetime(absen['TANGGAL'], format='%Y-%m-%d', errors='coerce')
    return db, absen, col_uang

db_df, absen_df, COL_UANG_SHIFT = load_data()

def get_uang_shift(id_kar, shift_code):
    if not shift_code: return "0"
    shift_code = str(shift_code).upper()
    dapat = any(x in shift_code for x in ['S2','S3','LS1','LS2'])
    if not dapat: return "0"
    try:
        val = db_df[db_df['ID KARYAWAN']==id_kar][COL_UANG_SHIFT].values[0]
        val = str(val).replace('Rp','').replace('.','').replace(',','').strip()
        if val == '' or val.lower()=='nan': return "0"
        return val
    except: return "0"

def bulatkan_ke_jam_pas(dt):
    return dt.replace(second=0, microsecond=0)

def cek_keterangan_dari_tanggal(tanggal_dt, jam_masuk_str="", jam_pulang_str="", jam_kerja_float=0, status="H"):
    tgl_str = tanggal_dt.strftime('%Y-%m-%d')
    weekday = tanggal_dt.weekday()
    if tgl_str in LIBUR_NASIONAL: return f"LIBUR NASIONAL: {LIBUR_NASIONAL[tgl_str]}"
    if jam_masuk_str and jam_pulang_str and jam_masuk_str!= jam_pulang_str and jam_kerja_float > 0: return "MASUK"
    if jam_kerja_float == 0:
        if status == 'L': return "SHIFT LIBUR"
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

def hitung(masuk_dt, pulang_dt, status):
    masuk_dt = bulatkan_ke_jam_pas(masuk_dt)
    pulang_dt = bulatkan_ke_jam_pas(pulang_dt)
    if pulang_dt < masuk_dt: pulang_dt += timedelta(days=1)
    total_mentah = (pulang_dt - masuk_dt).total_seconds() / 3600
    jam_float = total_mentah - 1.0 if total_mentah >= 6.0 else total_mentah
    if jam_float < 0: jam_float = 0

    tgl_str = masuk_dt.strftime('%Y-%m-%d')
    is_sabtu = masuk_dt.weekday() == 5
    is_minggu = masuk_dt.weekday() == 6
    is_merah = tgl_str in LIBUR_NASIONAL

    jam_masuk_str = masuk_dt.strftime('%H:%M:%S')
    jam_pulang_str = pulang_dt.strftime('%H:%M:%S')
    ket = cek_keterangan_dari_tanggal(masuk_dt, jam_masuk_str, jam_pulang_str, jam_float, status)
    shift = cek_shift(masuk_dt, pulang_dt, jam_float, ket, status)

    jk, jl, l15, l20 = hitung_lembur_lengkap(jam_float, is_sabtu, is_minggu, is_merah)
    return jk, jl, l15, l20, shift, ket, jam_masuk_str, jam_pulang_str

def upsert_absen(id_kar, masuk_dt, pulang_dt, nama, status="H", sudah_pulang=False):
    id_kar = id_kar.zfill(8)
    tgl_str = masuk_dt.strftime('%Y-%m-%d')
    STATUS_NON_JAM = ['A','I','S','C','L','GH','GHS','TL']
    if status in STATUS_NON_JAM:
        jam_masuk_str = ""; jam_pulang_str = ""; jam_kerja = "0.00"; jam_lembur = "0.00"; l1, l2 = "0.00", "0.00"
        shift = 'SL' if masuk_dt.strftime('%Y-%m-%d') in LIBUR_NASIONAL else status
        ket = cek_keterangan_dari_tanggal(masuk_dt, "", "", 0, status)
    elif not sudah_pulang:
        jam_masuk_str = masuk_dt.strftime('%H:%M:%S'); jam_pulang_str = ""; jam_kerja = "0.00"; jam_lembur = "0.00"; l1, l2 = "0.00", "0.00"
        shift = "-"; ket = "BELUM ABSEN PULANG"
    else:
        jam_kerja, jam_lembur, l1, l2, shift, ket, jam_masuk_str, jam_pulang_str = hitung(masuk_dt, pulang_dt, status)
    uang_shift = get_uang_shift(id_kar, shift)
    row_data = [id_kar, nama, tgl_str, jam_masuk_str, jam_pulang_str, jam_kerja, jam_lembur, l1, l2, shift, ket, status, uang_shift]
    existing = absen_df[(absen_df['ID KARYAWAN'] == id_kar) & (absen_df['TANGGAL'] == tgl_str)]
    if not existing.empty:
        row_num = existing.index[0] + 2
        ws_absen.update(f'A{row_num}:M{row_num}', [row_data])
    else:
        ws_absen.insert_row(row_data, 2)
    load_data.clear()

menu = st.tabs(["📝 ABSEN", "✏️ EDIT DATA", "⚙️ ADMIN", "📊 REKAP"])

with menu[0]:
    id_in = st.text_input("Masukkan ID Karyawan").strip().zfill(8)
    nama = ""
    if id_in:
        if id_in in db_df['ID KARYAWAN'].values:
            nama = db_df[db_df['ID KARYAWAN']==id_in]['NAMA KARYAWAN'].values[0]
            st.success(f"✅ {nama}")
        else: st.error("ID tidak ada")
    tgl = st.date_input("Tanggal Absen", datetime.now())
    data_hari_ini = absen_df[(absen_df['ID KARYAWAN'] == id_in) & (absen_df['TANGGAL'] == tgl.strftime('%Y-%m-%d'))] if id_in and not absen_df.empty else pd.DataFrame()
    sudah_masuk = not data_hari_ini.empty and data_hari_ini.iloc[0]['JAM MASUK']!= ""
    jam_masuk_lama = data_hari_ini.iloc[0]['JAM MASUK'] if sudah_masuk else ""
    col1, col2 = st.columns(2)
    with col1:
        jam_masuk = st.time_input("Jam Masuk", datetime.now().time())
        if st.button("🔵 ABSEN MASUK", use_container_width=True, type="primary", disabled=not nama):
            masuk_dt = datetime.combine(tgl, jam_masuk)
            upsert_absen(id_in, masuk_dt, masuk_dt, nama, "H", sudah_pulang=False)
            st.success("MASUK OK"); st.rerun()
    with col2:
        jam_pulang = st.time_input("Jam Pulang", datetime.now().time())
        if st.button("🔴 ABSEN PULANG", use_container_width=True, disabled=not nama):
            if not sudah_masuk: st.error("Belum absen masuk")
            else:
                masuk_dt = datetime.combine(tgl, datetime.strptime(jam_masuk_lama, '%H:%M:%S').time())
                pulang_dt = datetime.combine(tgl, jam_pulang)
                upsert_absen(id_in, masuk_dt, pulang_dt, nama, "H", sudah_pulang=True)
                st.success("PULANG OK"); st.rerun()

with menu[2]:
    st.warning("Fix data lama di SS")
    if st.button("🔥 FIX FINAL MINGGU 7 JAM X2.0 & SABTU 5+1.5+2.0", type="primary", use_container_width=True):
        all_vals = ws_absen.get_all_values()
        for i, row in enumerate(all_vals[1:], start=2):
            try:
                if len(row) < 5 or not row[3] or not row[4]: continue
                tgl = datetime.strptime(row[2], '%Y-%m-%d')
                masuk = datetime.strptime(row[3], '%H:%M:%S')
                pulang = datetime.strptime(row[4], '%H:%M:%S')
                masuk_dt = datetime.combine(tgl, masuk.time())
                pulang_dt = datetime.combine(tgl, pulang.time())
                if pulang_dt < masuk_dt: pulang_dt += timedelta(days=1)
                total = (pulang_dt - masuk_dt).total_seconds()/3600 - 1.0
                is_sabtu = tgl.weekday() == 5
                is_minggu = tgl.weekday() == 6
                is_merah = row[2] in LIBUR_NASIONAL
                jk, jl, l15, l20 = hitung_lembur_lengkap(total, is_sabtu, is_minggu, is_merah)
                ws_absen.update(f'F{i}:I{i}', [[jk, jl, l15, l20]])
            except: pass
        st.success("✅ FIX SELESAI"); load_data.clear(); st.rerun()

with menu[3]:
    st.dataframe(absen_df, use_container_width=True, height=600)
