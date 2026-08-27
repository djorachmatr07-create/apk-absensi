import streamlit as st
import gspread
import pandas as pd
import requests
import time
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from icalendar import Calendar

st.set_page_config(page_title="APK ABSENSI V1", layout="wide")
st.title("📍 APK ABSENSI V10.3 - AUTO BUAT LIBUR")

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

def hitung_lembur_baru(jam_kerja_float):
    try: jam_kerja_float = float(jam_kerja_float or 0)
    except: jam_kerja_float = 0.0
    jam_normal = 7.0
    lembur_1_5 = 0.0
    lembur_2_0 = 0.0
    if jam_kerja_float > jam_normal:
        jam_lembur_total = jam_kerja_float - jam_normal
        if jam_lembur_total > 0:
            lembur_1_5 = min(1.0, jam_lembur_total)
            if jam_lembur_total > 1.0:
                lembur_2_0 = jam_lembur_total - 1.0
    return f"{lembur_1_5:.2f}", f"{lembur_2_0:.2f}"

@st.cache_data(ttl=300)
def load_data():
    db = pd.DataFrame(ws_db.get_all_records())
    db['ID KARYAWAN'] = db['ID KARYAWAN'].astype(str).str.zfill(8)
    all_values = ws_absen.get_all_values()
    header = ['ID KARYAWAN', 'NAMA KARYAWAN', 'JAM MASUK', 'JAM PULANG', 'JAM KERJA', 'JAM LEMBUR', 'LEMBUR 1.5', 'LEMBUR 2.0', 'SHIFT', 'KETERANGAN', 'STATUS']
    if len(all_values) > 1:
        data = [row[:11] for row in all_values[1:]]
        absen = pd.DataFrame(data, columns=header) if data else pd.DataFrame(columns=header)
    else:
        absen = pd.DataFrame(columns=header)

    for col in header:
        if col not in absen.columns: absen[col] = ''

    if not absen.empty:
        absen['ID KARYAWAN'] = absen['ID KARYAWAN'].astype(str).str.zfill(8)
        absen['JAM MASUK DT'] = pd.to_datetime(absen['JAM MASUK'], format='%d/%m/%Y %H:%M:%S', errors='coerce')
        absen['JAM PULANG DT'] = pd.to_datetime(absen['JAM PULANG'], format='%d/%m/%Y %H:%M:%S', errors='coerce')
        absen['TGL'] = absen['JAM MASUK DT'].dt.strftime('%d/%m/%Y')
        absen = absen.sort_values('JAM MASUK DT', ascending=False)
    return db, absen

db_df, absen_df = load_data()

def bulatkan_ke_jam_pas(dt):
    if dt.minute >= 30: return dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else: return dt.replace(minute=0, second=0, microsecond=0)

def cek_keterangan_dari_tanggal(tanggal_dt, jam_masuk_str="", jam_pulang_str="", jam_kerja_float=0, status="H"):
    tgl_str = tanggal_dt.strftime('%Y-%m-%d')
    weekday = tanggal_dt.weekday()
    if tgl_str in LIBUR_NASIONAL:
        return f"LIBUR NASIONAL: {LIBUR_NASIONAL[tgl_str]}"
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
    total_jam_mentah = (pulang_dt - masuk_dt).total_seconds() / 3600
    jam_kerja_float = total_jam_mentah - 1.0 if total_jam_mentah >= 8.0 else total_jam_mentah
    if jam_kerja_float < 0: jam_kerja_float = 0
    jam_masuk_str = masuk_dt.strftime('%d/%m/%Y %H:%M:%S')
    jam_pulang_str = pulang_dt.strftime('%d/%m/%Y %H:%M:%S')
    keterangan = cek_keterangan_dari_tanggal(masuk_dt, jam_masuk_str, jam_pulang_str, jam_kerja_float, status)
    shift = cek_shift(masuk_dt, pulang_dt, jam_kerja_float, keterangan, status)
    lembur_1_5, lembur_2_0 = hitung_lembur_baru(jam_kerja_float)
    jam_lembur_total = float(lembur_1_5) + float(lembur_2_0)
    return f"{jam_kerja_float:.2f}", f"{jam_lembur_total:.2f}", lembur_1_5, lembur_2_0, shift, keterangan, jam_masuk_str, jam_pulang_str

def upsert_absen(id_kar, masuk_dt, pulang_dt, nama, status="H", sudah_pulang=False):
    id_kar = id_kar.zfill(8)
    tgl_str = masuk_dt.strftime('%d/%m/%Y') if masuk_dt else datetime.now().strftime('%d/%m/%Y')
    STATUS_NON_JAM = ['A','I','S','C','L','GH','GHS','TL']
    if status in STATUS_NON_JAM:
        jam_masuk_str = ""
        jam_pulang_str = ""
        jam_kerja = "0.00"
        jam_lembur = "0.00"
        l1, l2 = "0.00", "0.00"
        shift = 'SL' if masuk_dt.strftime('%Y-%m-%d') in LIBUR_NASIONAL else status
        ket = cek_keterangan_dari_tanggal(masuk_dt, "", 0, status)
    elif not sudah_pulang:
        jam_masuk_str = masuk_dt.strftime('%d/%m/%Y %H:%M:%S')
        jam_pulang_str = ""
        jam_kerja = "0.00"
        jam_lembur = "0.00"
        l1, l2 = "0.00", "0.00"
        shift = "-"
        ket = "BELUM ABSEN PULANG"
    else:
        jam_kerja, jam_lembur, l1, l2, shift, ket, jam_masuk_str, jam_pulang_str = hitung(masuk_dt, pulang_dt, status)
    
    row_data = [id_kar, nama, jam_masuk_str, jam_pulang_str, jam_kerja, jam_lembur, l1, l2, shift, ket, status]
    existing = absen_df[(absen_df['ID KARYAWAN'] == id_kar) & (absen_df['TGL'] == tgl_str)]
    
    if not existing.empty:
        row_num = existing.index[0] + 2
        ws_absen.update(f'A{row_num}:K{row_num}', [row_data])
    else:
        ws_absen.insert_row(row_data, 2)
    load_data.clear()

# INI BARU: AUTO BUAT DATA LIBUR NASIONAL
def update_semua_keterangan():
    if db_df.empty: return 0
    total_update = 0
    progress_bar = st.progress(0, text="Mulai update...")
    
    # 1. UPDATE DATA LAMA
    updates = []
    for i, row in absen_df.iterrows():
        if row['JAM MASUK'] and row['JAM PULANG']:
            masuk_dt = pd.to_datetime(row['JAM MASUK'])
            pulang_dt = pd.to_datetime(row['JAM PULANG'])
            status_lama = row.get('STATUS', 'H')
            jam_kerja, jam_lembur, l1, l2, shift, ket, _, _ = hitung(masuk_dt, pulang_dt, status_lama)
        else:
            status_lama = row.get('STATUS', 'H')
            jam_kerja, jam_lembur, l1, l2 = "0.00", "0.00", "0.00", "0.00"
            masuk_dt = pd.to_datetime(row['JAM MASUK']) if row['JAM MASUK'] else datetime.now()
            shift = 'SL' if masuk_dt.strftime('%Y-%m-%d') in LIBUR_NASIONAL else status_lama
            ket = cek_keterangan_dari_tanggal(masuk_dt, "", "", 0, status_lama)

        row_num = i + 2
        updates.append({'range': f'E{row_num}:K{row_num}', 'values': [[jam_kerja, jam_lembur, l1, l2, shift, ket, status_lama]]})
        total_update += 1
    
    # 2. BUAT DATA BARU UNTUK LIBUR NASIONAL YG BELUM ADA
    for tgl_libur_str, nama_libur in LIBUR_NASIONAL.items():
        tgl_libur_dt = datetime.strptime(tgl_libur_str, '%Y-%m-%d')
        tgl_libur_format = tgl_libur_dt.strftime('%d/%m/%Y')
        
        for _, kar in db_df.iterrows():
            id_kar = kar['ID KARYAWAN']
            nama_kar = kar['NAMA KARYAWAN']
            # cek apakah karyawan ini sudah ada data di tgl libur
            ada = absen_df[(absen_df['ID KARYAWAN'] == id_kar) & (absen_df['TGL'] == tgl_libur_format)]
            if ada.empty:
                # buat data baru status L
                row_data = [id_kar, nama_kar, "", "", "0.00", "0.00", "0.00", "0.00", "SL", f"LIBUR NASIONAL: {nama_libur}", "L"]
                ws_absen.insert_row(row_data, 2)
                total_update += 1
    
    if updates: ws_absen.batch_update(updates)
    progress_bar.progress(1.0, text="Selesai")
    progress_bar.empty()
    load_data.clear()
    return total_update

menu = st.tabs(["📝 ABSEN", "✏️ EDIT DATA", "⚙️ ADMIN", "📊 REKAP"])

with menu[0]:
    id_in = st.text_input("Masukkan ID Karyawan", key="id_absen").strip().zfill(8)
    nama = ""
    if id_in:
        if id_in in db_df['ID KARYAWAN'].values:
            nama = db_df[db_df['ID KARYAWAN']==id_in]['NAMA KARYAWAN'].values[0]
            st.success(f"✅ Nama: {nama}")
        else: st.error(f"ID {id_in} tidak ada")
    tgl = st.date_input("Tanggal Absen", datetime.now(), key="tgl_absen")
    tgl_str = tgl.strftime('%d/%m/%Y')
    data_hari_ini = pd.DataFrame()
    if id_in and not absen_df.empty:
        data_hari_ini = absen_df[(absen_df['ID KARYAWAN'] == id_in) & (absen_df['TGL'] == tgl_str)]
    with st.expander("⚙️ Ubah Status Khusus: GH, GHS, TL, I, S, C, A"):
        DAFTAR_STATUS_ABSEN = {"H": "H - HADIR NORMAL", "GH": "GH - GANTI HARI", "GHS": "GHS - GANTI HARI SABTU", "TL": "TL - TUKAR LIBUR", "I": "I - IZIN", "S": "S - SAKIT", "C": "C - CUTI", "A": "A - ALFA"}
        status_pilih = st.selectbox("Pilih Status Khusus", options=list(DAFTAR_STATUS_ABSEN.keys()), format_func=lambda x: DAFTAR_STATUS_ABSEN[x], index=0, key="status_absen")
    if status_pilih!= "H":
        if st.button(f"SIMPAN STATUS {status_pilih}", use_container_width=True, type="primary", key="btn_status"):
            upsert_absen(id_in, datetime.now(), datetime.now(), nama, status_pilih)
            st.balloons(); st.success(f"✅ Status {DAFTAR_STATUS_ABSEN[status_pilih]} berhasil disimpan"); st.rerun()
    else:
        if data_hari_ini.empty:
            st.info("📌 Silahkan Absen Masuk Dulu")
            jam_masuk = st.time_input("Jam Masuk", datetime.now().time(), key="jam_masuk_absen")
            if st.button("🔵 ABSEN MASUK", use_container_width=True, type="primary", disabled=not nama, key="btn_masuk"):
                masuk_dt = datetime.combine(tgl, jam_masuk)
                upsert_absen(id_in, masuk_dt, masuk_dt, nama, "H", sudah_pulang=False)
                st.balloons(); st.success(f"✅ ABSEN MASUK BERHASIL!\nJam: {masuk_dt.strftime('%H:%M')}"); st.rerun()
        else:
            data = data_hari_ini.iloc[0]
            if data['JAM MASUK']: st.success(f"📌 Sudah Absen Masuk: {pd.to_datetime(data['JAM MASUK']).strftime('%H:%M')}")
            if data['JAM PULANG'] == "":
                jam_pulang = st.time_input("Jam Pulang", datetime.now().time(), key="jam_pulang_absen")
                if st.button("🔴 ABSEN PULANG", use_container_width=True, type="secondary", key="btn_pulang"):
                    masuk_dt = pd.to_datetime(data['JAM MASUK'])
                    pulang_dt = datetime.combine(tgl, jam_pulang)
                    upsert_absen(id_in, masuk_dt, pulang_dt, nama, "H", sudah_pulang=True)
                    st.balloons(); st.success(f"✅ ABSEN PULANG BERHASIL!\nJam: {pulang_dt.strftime('%H:%M')}"); st.rerun()
            else: st.info(f"✅ Sudah Absen Lengkap")

with menu[1]:
    if "login" not in st.session_state: st.session_state.login = False
    if not st.session_state.login:
        pw = st.text_input("Password Admin", type="password", key="pw_edit")
        if st.button("LOGIN", key="btn_login"):
            if pw == PASSWORD_ADMIN: st.session_state.login = True; st.rerun()
            else: st.error("Password Salah")
    else:
        if st.button("LOGOUT", key="btn_logout"): st.session_state.login = False; st.rerun()
        id_edit = st.text_input("ID yg mau diedit", key="id_edit").strip().zfill(8)
        if id_edit in db_df['ID KARYAWAN'].values:
            data_kar = absen_df[absen_df['ID KARYAWAN']==id_edit]
            if not data_kar.empty:
                opsi_tgl = data_kar.dropna(subset=['JAM MASUK DT']).sort_values('JAM MASUK DT')['JAM MASUK'].tolist()
                pilih = st.selectbox("Pilih Tanggal Data", opsi_tgl, key="pilih_tgl_edit")
                row = data_kar[data_kar['JAM MASUK']==pilih].iloc[0]
                
                col1, col2 = st.columns(2)
                with col1:
                    tgl_edit = st.date_input("Tanggal", pd.to_datetime(row['JAM MASUK']).date(), key="tgl_edit")
                    jam_masuk_edit = st.time_input("Jam Masuk", pd.to_datetime(row['JAM MASUK']).time() if row['JAM MASUK'] else datetime.now().time(), key="jam_masuk_edit")
                with col2:
                    jam_pulang_edit = st.time_input("Jam Pulang", pd.to_datetime(row['JAM PULANG']).time() if row['JAM PULANG'] else datetime.now().time(), key="jam_pulang_edit")
                
                DAFTAR_STATUS_EDIT = {"H": "H - HADIR", "GH": "GH - GANTI HARI", "GHS": "GHS - GANTI HARI SABTU", "TL": "TL - TUKAR LIBUR", "A": "A - ALFA", "I": "I - IZIN", "S": "S - SAKIT", "C": "C - CUTI", "L": "L - LIBUR"}
                kode_pilih = st.selectbox("Ubah Status Menjadi", options=list(DAFTAR_STATUS_EDIT.keys()), format_func=lambda x: DAFTAR_STATUS_EDIT[x], key="status_edit")
                
                if st.button("SIMPAN EDIT", use_container_width=True, type="primary", key="btn_simpan_edit"):
                    with st.spinner("Menyimpan data..."):
                        time.sleep(0.3)
                        masuk_dt = datetime.combine(tgl_edit, jam_masuk_edit)
                        pulang_dt = datetime.combine(tgl_edit, jam_pulang_edit)
                        upsert_absen(id_edit, masuk_dt, pulang_dt, row['NAMA KARYAWAN'], kode_pilih, sudah_pulang=True)
                    st.success(f"✅ Edit berhasil. Status: {DAFTAR_STATUS_EDIT[kode_pilih]}"); st.rerun()

with menu[2]:
    st.warning("⚠️ Klik ini untuk buat otomatis data libur nasional + update data lama")
    if st.button("🔄 UPDATE SEMUA DATA", type="primary", use_container_width=True, key="btn_update"):
        jml = update_semua_keterangan()
        st.success(f"✅ Selesai! {jml} data diproses. Refresh Google Sheet Ctrl+R")

with menu[3]:
    st.dataframe(absen_df, use_container_width=True, height=600)
