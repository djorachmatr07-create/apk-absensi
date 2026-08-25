import streamlit as st
import gspread
import requests
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="APK ABSENSI", layout="centered")
st.title("📍 APK ABSENSI KARYAWAN")

# 1. KONEK KE SHEET
@st.cache_resource
def connect_gsheet():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(creds)
    sh = client.open("REKAP")
    return sh.worksheet("REKAP ABSENSI"), sh.worksheet("DATABASE KARYAWAN")

ws_absen, ws_db = connect_gsheet()
st.success("✅ Konek ke Google Sheet Berhasil")

# 2. AMBIL DATA LIBUR NASIONAL DARI API
@st.cache_data(ttl=86400)
def get_libur_nasional(tahun):
    try:
        url = f"https://indonesia-holiday-api.vercel.app/api/{tahun}"
        res = requests.get(url, timeout=5)
        data = res.json()
        set_libur = {item['holiday_date'] for item in data}
        return set_libur
    except:
        st.warning("Gagal ambil data libur nasional. Cek koneksi internet.")
        return set()

# 3. BACA DATABASE
@st.cache_data(ttl=300)
def load_db():
    data_db = ws_db.get_all_records()
    return {str(row['ID KARYAWAN']): row['NAMA'] for row in data_db}

db_dict = load_db()

# 4. PASTIIN HEADER
headers = ["ID KARYAWAN", "JAM MASUK", "JAM PULANG", "NAMA KARYAWAN", "JAM KERJA", "JAM LEMBUR", "SHIFT", "KETERANGAN"]
if ws_absen.row_values(1)!= headers:
    ws_absen.update('A1:H1', [headers])

# 5. INPUT ID + AUTO NAMA
id_karyawan = st.text_input("1. Masukkan ID Karyawan")
nama = ""
if id_karyawan:
    nama = db_dict.get(id_karyawan, "")
    if nama:
        st.text_input("2. Nama Karyawan", value=nama, disabled=True)
    else:
        st.error("ID tidak ditemukan di DATABASE KARYAWAN")

st.markdown("---")

# 6. PILIH JAM MANUAL / OTOMATIS
opsi_jam = st.radio("3. Waktu Absen:", ["Jam Sekarang", "Pilih Hari & Jam Manual"], horizontal=True, key="opsi")
if opsi_jam == "Jam Sekarang":
    waktu_absen = datetime.now()
else:
    col_tgl, col_jam = st.columns(2)
    with col_tgl:
        tanggal = st.date_input("Pilih Tanggal", value=datetime.now().date(), key="tgl")
    with col_jam:
        jam = st.time_input("Pilih Jam", value=datetime.now().time(), key="jam")
    waktu_absen = datetime.combine(tanggal, jam)

# 7. PILIHAN BARU: STATUS HARI
status_hari = st.selectbox(
    "4. Status Hari",
    ["NORMAL", "TUKAR HARI", "LIBUR"],
    help="NORMAL = hari biasa. TUKAR HARI = hari kerja dipindah. LIBUR = paksa lembur x2"
)

st.text_input("5. SHIFT OTOMATIS", value="Akan ditentukan saat pulang", disabled=True)
set_libur = get_libur_nasional(waktu_absen.year)

# 8. FUNGSI BANTU LENGKAP
def bulat_masuk(dt_obj):
    if dt_obj.minute > 0 or dt_obj.second > 0:
        return (dt_obj + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    return dt_obj.replace(minute=0, second=0, microsecond=0)

def bulat_pulang(dt_obj):
    return dt_obj.replace(minute=0, second=0, microsecond=0)

def hitung_lembur_multiplier(total_lembur_jam, multiplier=2.0):
    return f"{total_lembur_jam * multiplier:.2f}"

def tentukan_shift(masuk_dt, pulang_dt):
    total_jam_bersih = ((pulang_dt - masuk_dt).total_seconds() / 3600) - 1
    jam_masuk = masuk_dt.hour
    if 7 <= jam_masuk < 8 and total_jam_bersih >= 10: return "LONG SHIFT1 07-18"
    if 19 <= jam_masuk < 20 and total_jam_bersih >= 10: return "LONG SHIFT2 19-07"
    jam_pulang = pulang_dt.hour * 60 + pulang_dt.minute
    if 900 <= jam_pulang < 1380: return "SHIFT 1"
    if jam_pulang >= 1380 or jam_pulang < 420: return "SHIFT 2"
    return "SHIFT 3"

def hitung_jam(masuk_str, pulang_str, set_libur, status_hari):
    if not masuk_str or not pulang_str: return "0:00:00", "0.00", "", ""
    fmt = '%d/%m/%Y %H:%M:%S'
    masuk = datetime.strptime(masuk_str, fmt)
    pulang = datetime.strptime(pulang_str, fmt)

    masuk_bulat = bulat_masuk(masuk)
    pulang_bulat = bulat_pulang(pulang)
    total_jam_mentah = (pulang_bulat - masuk_bulat).total_seconds() / 3600
    tanggal_api_format = masuk.strftime('%Y-%m-%d')
    weekday = masuk.weekday()
    is_libur_api = (weekday == 6) or (tanggal_api_format in set_libur)

    # RULE BARU: PRIORITAS STATUS HARI
    is_libur = False
    keterangan = ""

    if status_hari == "LIBUR": # Paksa lembur
        is_libur = True
        keterangan = "LEMBUR"
    elif status_hari == "TUKAR HARI": # Hari libur jadi kerja normal
        is_libur = False
        keterangan = "TUKAR HARI"
    else: # NORMAL
        is_libur = is_libur_api
        if is_libur: keterangan = "LEMBUR"
        elif weekday == 5: keterangan = "SABTU"
        else: keterangan = "HARI KERJA"

    is_sabtu_full = False
    jam_kerja_float = 0.0
    lembur_jam = 0.0
    lembur_multiplier = "0.00"

    if is_libur:
        total_jam_bersih = total_jam_mentah - 1
        if total_jam_bersih < 0: total_jam_bersih = 0
        jam_kerja_float = 0.0
        lembur_jam = total_jam_bersih
        lembur_multiplier = hitung_lembur_multiplier(lembur_jam, 2.0)
    elif weekday == 5 and status_hari == "NORMAL": # SABTU NORMAL
        total_jam_bersih = total_jam_mentah
        jam_efektif = 5.0
        if total_jam_bersih >= 8.0:
            total_jam_bersih -= 1.0
            is_sabtu_full = True
            keterangan = "SABTU FULL DAY"
        lembur_jam = total_jam_bersih - jam_efektif
        if lembur_jam < 0: lembur_jam = 0
        jam_kerja_float = jam_efektif if total_jam_bersih >= jam_efektif else total_jam_bersih
        if lembur_jam > 0:
            jam_pertama = 1.0 if lembur_jam >= 1 else lembur_jam
            sisa = lembur_jam - jam_pertama
            lembur_efektif = (jam_pertama * 1.5) + (sisa * 2.0)
            lembur_multiplier = f"{lembur_efektif:.2f}"
    else: # SENIN - JUMAT / TUKAR HARI
        total_jam_bersih = total_jam_mentah - 1
        if total_jam_bersih < 0: total_jam_bersih = 0
        jam_efektif = 7.0
        lembur_jam = total_jam_bersih - jam_efektif
        if lembur_jam < 0: lembur_jam = 0
        jam_kerja_float = jam_efektif if total_jam_bersih >= jam_efektif else total_jam_bersih
        if lembur_jam > 0:
            jam_pertama = 1.0 if lembur_jam >= 1 else lembur_jam
            sisa = lembur_jam - jam_pertama
            lembur_efektif = (jam_pertama * 1.5) + (sisa * 2.0)
            lembur_multiplier = f"{lembur_efektif:.2f}"

    jam_kerja = f"{int(jam_kerja_float)}:00:00"
    shift_final = tentukan_shift(masuk_bulat, pulang_bulat)
    return jam_kerja, lembur_multiplier, shift_final, keterangan

def sudah_absen_masuk(id_kar, tanggal_str, all_data):
    for row in all_data[1:]:
        if row[0] == id_kar and row[1]:
            tgl_db = datetime.strptime(row[1], '%d/%m/%Y %H:%M:%S').strftime('%d/%m/%Y')
            if tgl_db == tanggal_str:
                return True
    return False

def cari_data_belum_pulang(id_kar, all_data):
    for i in range(len(all_data)-1, 0, -1):
        row = all_data[i]
        if row[0] == id_kar and row[2] == "":
            return i + 1
    return None

# 9. TOMBOL ABSEN + RECALCULATE
col1, col2, col3 = st.columns(3)
all_data = ws_absen.get_all_values()
tanggal_hari_ini = waktu_absen.strftime('%d/%m/%Y')

with col1:
    if st.button("ABSEN MASUK", use_container_width=True):
        if id_karyawan and nama:
            if sudah_absen_masuk(id_karyawan, tanggal_hari_ini, all_data):
                st.error(f"❌ Gagal! {nama} sudah absen masuk di tanggal {tanggal_hari_ini}")
            else:
                datetime_str = waktu_absen.strftime('%d/%m/%Y %H:%M:%S')
                row = [id_karyawan, datetime_str, "", nama, "", "0.00", "", ""]
                ws_absen.append_row(row, value_input_option='USER_ENTERED')
                st.success(f"✅ Absen Masuk: {datetime_str}")
                st.cache_data.clear()
        else: st.warning("Isi ID yang benar dulu min")

with col2:
    if st.button("ABSEN PULANG", use_container_width=True):
        if id_karyawan and nama:
            row_index = cari_data_belum_pulang(id_karyawan, all_data)
            if row_index:
                datetime_str = waktu_absen.strftime('%d/%m/%Y %H:%M:%S')
                jam_masuk = ws_absen.cell(row_index, 2).value
                ws_absen.update_cell(row_index, 3, datetime_str)
                jam_kerja, jam_lembur, shift, ket = hitung_jam(jam_masuk, datetime_str, set_libur, status_hari)
                ws_absen.update_cell(row_index, 5, jam_kerja)
                ws_absen.update_cell(row_index, 6, jam_lembur)
                ws_absen.update_cell(row_index, 7, shift)
                ws_absen.update_cell(row_index, 8, ket)
                st.success(f"✅ Absen Pulang: {datetime_str}")
                st.info(f"Shift: {shift} | Kerja: {jam_kerja} | Lembur: {jam_lembur} Jam | {ket}")
                st.cache_data.clear()
            else: st.error("❌ Tidak ada data absen masuk yg belum pulang")
        else: st.warning("Isi ID yang benar dulu min")

with col3:
    if st.button("🔄 RECALCULATE", use_container_width=True):
        st.info("Pilih status hari dulu baru klik ini")
