import streamlit as st
import gspread
import pandas as pd
import requests
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from icalendar import Calendar

st.set_page_config(page_title="APK ABSENSI V1", layout="wide")
st.title("📍 APK V8.5")

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
    absen = pd.DataFrame(ws_absen.get_all_records())
    for col in ['STATUS', 'JAM LEMBUR', 'JAM KERJA', 'SHIFT', 'KETERANGAN']:
        if col not in absen.columns: absen[col] = ''
    if not absen.empty:
        absen['ID KARYAWAN'] = absen['ID KARYAWAN'].astype(str).str.zfill(8)
        absen['JAM MASUK DT'] = pd.to_datetime(absen['JAM MASUK'], format='%d/%m/%Y %H:%M:%S', errors='coerce')
        absen['TGL'] = absen['JAM MASUK DT'].dt.strftime('%d/%m/%Y')
    else:
        absen = pd.DataFrame(columns=["ID KARYAWAN", "NAMA KARYAWAN", "JAM MASUK", "JAM PULANG", "JAM KERJA", "JAM LEMBUR", "SHIFT", "KETERANGAN", "STATUS", "JAM MASUK DT", "TGL"])
    return db, absen

db_df, absen_df = load_data()

def bulatkan_ke_jam_pas(dt):
    if dt.minute >= 30: return dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else: return dt.replace(minute=0, second=0, microsecond=0)

def cek_keterangan_dari_tanggal(tanggal_dt, jam_masuk_str, jam_pulang_str, jam_kerja_float, status):
    tgl_str = tanggal_dt.strftime('%Y-%m-%d')
    weekday = tanggal_dt.weekday()
    if jam_masuk_str and jam_pulang_str and jam_masuk_str!= jam_pulang_str and jam_kerja_float > 0:
        return "MASUK"
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

def cek_shift(jam_masuk_dt, jam_kerja_float, keterangan, status):
    if 'LIBUR' in keterangan: return 'SL'
    if status in ['A','I','S','C','TL']: return status
    if jam_kerja_float == 0: return '-'
    if jam_kerja_float >= 11.5: shift_code = 'LS'
    else:
        jam = jam_masuk_dt.hour
        if 7 <= jam < 15: shift_code = 'S1'
        elif 15 <= jam < 23: shift_code = 'S2'
        else: shift_code = 'S3'
    if keterangan == "MASUK":
        return f"{status}-{shift_code}"
    else:
        return shift_code

def hitung_lembur(jam_kerja_float):
    jam_normal = 8.0
    jam_lembur = 0.0
    if jam_kerja_float > jam_normal: jam_lembur = jam_kerja_float - jam_normal
    return f"{jam_lembur:.2f}"

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
    shift = cek_shift(masuk_dt, jam_kerja_float, keterangan, status)
    jam_lembur = hitung_lembur(jam_kerja_float)
    return f"{jam_kerja_float:.2f}", jam_lembur, shift, keterangan, jam_masuk_str, jam_pulang_str

def upsert_absen(id_kar, masuk_dt, pulang_dt, nama, status="H", sudah_pulang=False):
    id_kar = id_kar.zfill(8)
    tgl_str = masuk_dt.strftime('%d/%m/%Y') if masuk_dt else tgl_str
    
    STATUS_NON_JAM = ['A','I','S','C','L']
    
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
    
    if not absen_df.empty:
        existing = absen_df[(absen_df['ID KARYAWAN'] == id_kar) & (absen_df['TGL'] == tgl_str)]
    else: existing = pd.DataFrame()
    
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

with menu[0]:
    id_in = st.text_input("Masukkan ID Karyawan").strip().zfill(8)
    nama = ""
    if id_in:
        if id_in in db_df['ID KARYAWAN'].values:
            nama = db_df[db_df['ID KARYAWAN']==id_in]['NAMA KARYAWAN'].values[0]
            st.success(f"✅ Nama: {nama}")
        else:
            st.error(f"ID {id_in} tidak ada")

    tgl = st.date_input("Tanggal", datetime.now())
    tgl_str = tgl.strftime('%d/%m/%Y')

    data_hari_ini = pd.DataFrame()
    if id_in and not absen_df.empty:
        data_hari_ini = absen_df[(absen_df['ID KARYAWAN'] == id_in) & (absen_df['TGL'] == tgl_str)]

    with st.expander("⚙️ Ubah Status Khusus: GH, GHS, TL, I, S, C, A"):
        DAFTAR_STATUS_ABSEN = {
            "H": "H - HADIR NORMAL", "GH": "GH - GANTI HARI", "GHS": "GHS - GANTI HARI SABTU",
            "TL": "TL - TUKAR LIBUR", "I": "I - IZIN", "S": "S - SAKIT", "C": "C - CUTI", "A": "A - ALFA"
        }
        status_pilih = st.selectbox("Pilih Status Khusus", options=list(DAFTAR_STATUS_ABSEN.keys()), format_func=lambda x: DAFTAR_STATUS_ABSEN[x], index=0)

    if status_pilih!= "H":
        if st.button(f"SIMPAN STATUS {status_pilih}", use_container_width=True, type="primary"):
            upsert_absen(id_in, datetime.now(), datetime.now(), nama, status_pilih)
            st.balloons()
            st.success(f"✅ Status {DAFTAR_STATUS_ABSEN[status_pilih]} berhasil disimpan")
            st.rerun()
    else:
        if data_hari_ini.empty:
            st.info("📌 Silahkan Absen Masuk Dulu")
            jam_masuk = st.time_input("Jam Masuk", datetime.now().time())
            if st.button("🔵 ABSEN MASUK", use_container_width=True, type="primary", disabled=not nama):
                masuk_dt = datetime.combine(tgl, jam_masuk)
                upsert_absen(id_in, masuk_dt, masuk_dt, nama, "H", sudah_pulang=False)
                st.balloons()
                st.success(f"✅ ABSEN MASUK BERHASIL!\nJam: {masuk_dt.strftime('%H:%M')}")
                st.rerun()
        else:
            data = data_hari_ini.iloc[0]
            if data['JAM MASUK']: st.success(f"📌 Sudah Absen Masuk: {pd.to_datetime(data['JAM MASUK']).strftime('%H:%M')}")
            if data['JAM PULANG'] == "":
                jam_pulang = st.time_input("Jam Pulang", datetime.now().time())
                if st.button("🔴 ABSEN PULANG", use_container_width=True, type="secondary"):
                    masuk_dt = pd.to_datetime(data['JAM MASUK'])
                    pulang_dt = datetime.combine(tgl, jam_pulang)
                    upsert_absen(id_in, masuk_dt, pulang_dt, nama, "H", sudah_pulang=True)
                    st.balloons()
                    st.success(f"✅ ABSEN PULANG BERHASIL!\nJam: {pulang_dt.strftime('%H:%M')}")
                    st.rerun()
            else:
                st.info(f"✅ Sudah Absen Lengkap")

with menu[1]:
    if "login" not in st.session_state: st.session_state.login = False
    if not st.session_state.login:
        pw = st.text_input("Password Admin", type="password")
        if st.button("LOGIN"):
            if pw == PASSWORD_ADMIN: st.session_state.login = True; st.rerun()
            else: st.error("Password Salah")
    else:
        if st.button("LOGOUT"): st.session_state.login = False; st.rerun()
        id_edit = st.text_input("ID yg mau diedit").strip().zfill(8)
        if id_edit in db_df['ID KARYAWAN'].values:
            data_kar = absen_df[absen_df['ID KARYAWAN']==id_edit]
            if not data_kar.empty:
                pilih = st.selectbox("Pilih Tanggal", data_kar.sort_values('JAM MASUK DT')['JAM MASUK'].tolist())
                row = data_kar[data_kar['JAM MASUK']==pilih].iloc[0]
                DAFTAR_STATUS_EDIT = {
                    "H": "H - HADIR", "GH": "GH - GANTI HARI", "GHS": "GHS - GANTI HARI SABTU",
                    "TL": "TL - TUKAR LIBUR", "A": "A - ALFA", "I": "I - IZIN",
                    "S": "S - SAKIT", "C": "C - CUTI", "L": "L - LIBUR"
                }
                kode_pilih = st.selectbox("Ubah Status Menjadi", options=list(DAFTAR_STATUS_EDIT.keys()), format_func=lambda x: DAFTAR_STATUS_EDIT[x])
                if st.button("SIMPAN EDIT"):
                    masuk_dt = pd.to_datetime(row['JAM MASUK']) if row['JAM MASUK'] else datetime.now()
                    pulang_dt = pd.to_datetime(row['JAM PULANG']) if row['JAM PULANG'] else datetime.now()
                    upsert_absen(id_edit, masuk_dt, pulang_dt, row['NAMA KARYAWAN'], kode_pilih)
                    st.success(f"✅ Edit berhasil. Status: {DAFTAR_STATUS_EDIT[kode_pilih]}")
                    st.rerun()

with menu[2]: # INI YANG KOSONG TADI
    st.warning("Menu untuk update data lama dan setting admin")
    if st.button("🔄 UPDATE SEMUA DATA", type="primary", use_container_width=True):
        with st.spinner("Mohon tunggu..."):
            jml = update_semua_keterangan()
            st.success(f"✅ Selesai! {jml} data diupdate")
            st.rerun()

with menu[3]:
    st.dataframe(absen_df.sort_values('JAM MASUK DT', ascending=False), use_container_width=True, height=600)
