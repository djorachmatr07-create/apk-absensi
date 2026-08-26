import streamlit as st
import gspread
import pandas as pd
from datetime import datetime
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="APK ABSENSI V1", layout="wide")
st.title("📍 APK ABSENSI KARYAWAN V5.1")

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
st.success(f"✅ Konek. Karyawan: {len(db_df)} | Data Absen: {len(absen_df)}")

# LIBUR NASIONAL 2026 FIX SESUAI SKB + KALENDER KAMU
LIBUR_NASIONAL = {
    "2026-01-01": "Tahun Baru 2026",
    "2026-01-29": "Tahun Baru Imlek 2577 Kongzili",
    "2026-02-14": "Isra Mikraj Nabi Muhammad SAW",
    "2026-03-19": "Hari Suci Nyepi Tahun Baru Saka 1948",
    "2026-03-20": "Cuti Bersama Hari Suci Nyepi",
    "2026-03-29": "Wafat Isa Al Masih",
    "2026-03-30": "Cuti Bersama Wafat Isa Al Masih",
    "2026-04-21": "Hari Raya Idul Fitri 1447 H",
    "2026-04-22": "Hari Raya Idul Fitri 1447 H",
    "2026-04-23": "Cuti Bersama Idul Fitri 1447 H",
    "2026-04-24": "Cuti Bersama Idul Fitri 1447 H",
    "2026-05-01": "Hari Buruh Internasional",
    "2026-05-14": "Kenaikan Isa Al Masih",
    "2026-05-27": "Hari Raya Waisak 2560 BE",
    "2026-05-28": "Cuti Bersama Hari Raya Waisak",
    "2026-06-01": "Hari Lahir Pancasila",
    "2026-06-17": "Hari Raya Idul Adha 1447 H",
    "2026-06-18": "Cuti Bersama Hari Raya Idul Adha",
    "2026-06-27": "1 Muharram 1448 H - Tahun Baru Islam",
    "2026-08-17": "Hari Kemerdekaan Republik Indonesia", # SENIN
    "2026-08-25": "Maulid Nabi Muhammad SAW", # SELASA - INI YG KEMARIN KELEWAT
    "2026-08-28": "Cuti Bersama Maulid Nabi Muhammad SAW",
    "2026-12-25": "Hari Raya Natal",
}
st.info(f"✅ Data Kalender Nasional Loaded: {len(LIBUR_NASIONAL)} hari libur/cuti")

def cek_keterangan_dari_tanggal(tanggal_dt, jam_masuk_str, jam_pulang_str, jam_kerja_float):
    tgl_str = tanggal_dt.strftime('%Y-%m-%d')
    weekday = tanggal_dt.weekday()

    # RULE 1: KALAU ADA JAM MASUK DAN PULANG BEDA = MASUK
    if jam_masuk_str and jam_pulang_str and jam_masuk_str!= jam_pulang_str and jam_kerja_float > 0:
        return "MASUK"

    # RULE 2: KALAU JAM KERJA 0 BARU CEK KALENDER
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
    if st.button("🔄 UPDATE SEMUA KETERANGAN DARI KALENDER", use_container_width=True, type="primary"):
        with st.spinner("Sedang update semua data..."):
            jml = update_semua_keterangan()
        st.success(f"✅ Selesai! {jml} data diupdate")
        st.rerun()
    if st.button("🗑️ REFRESH DATA", use_container_width=True):
        load_data.clear()
        st.rerun()
    if not absen_df.empty:
        st.dataframe(absen_df.sort_values('JAM MASUK DT', ascending=False), use_container_width=True)
