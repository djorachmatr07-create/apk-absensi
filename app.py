import streamlit as st
import gspread
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="APK ABSENSI", layout="centered")
st.title("📍 APK ABSENSI KARYAWAN")

# 1. KONEK KE SHEET
try:
    creds_dict = st.secrets["gcp_service_account"]
    scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets', "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sh = client.open("REKAP")
    ws_absen = sh.worksheet("REKAP ABSENSI")
    ws_db = sh.worksheet("DATABASE KARYAWAN")
    st.success("✅ Konek ke Google Sheet Berhasil")
except Exception as e:
    st.error(f"Gagal konek: {e}")
    st.stop()

# 2. BACA DATABASE NAMA
data_db = ws_db.get_all_records()
db_dict = {str(row['ID KARYAWAN']).lstrip('0'): row['NAMA'] for row in data_db}

# 3. PASTIIN HEADER BENAR: TANPA JAM LEMBUR
headers = ["ID KARYAWAN", "JAM MASUK", "JAM PULANG", "NAMA KARYAWAN", "JAM KERJA", "SHIFT"]
if ws_absen.row_values(1)!= headers:
    ws_absen.update('A1:F1', [headers])

# 4. INPUT ID + AUTO NAMA
id_karyawan = st.text_input("Masukkan ID Karyawan")
nama = ""
if id_karyawan:
    id_cari = id_karyawan.lstrip('0')
    nama = db_dict.get(id_cari, "")
    if nama:
        st.text_input("Nama Karyawan", value=nama, disabled=True)
    else:
        st.error("ID tidak ditemukan di DATABASE KARYAWAN")

st.markdown("---")
# 5. PILIH JAM MANUAL / OTOMATIS
opsi_jam = st.radio("Waktu Absen:", ["Jam Sekarang", "Jam Manual"], horizontal=True)
if opsi_jam == "Jam Sekarang":
    waktu_absen = datetime.now()
else:
    tanggal = st.date_input("Tanggal")
    jam = st.time_input("Jam")
    waktu_absen = datetime.combine(tanggal, jam)
datetime_str = waktu_absen.strftime('%d/%m/%Y %H:%M:%S')

# 6. FUNGSI HITUNG 7 JAM KERJA
def hitung_shift(masuk, pulang):
    total_jam = (pulang - masuk).total_seconds() / 3600 - 1 # -1 jam istirahat
    jam_masuk = masuk.hour
    if 7 <= jam_masuk < 8 and total_jam >= 10: return "LONG SHIFT1 07-18"
    if 19 <= jam_masuk < 20 and total_jam >= 10: return "LONG SHIFT2 19-07"
    jam_pulang = pulang.hour * 60 + pulang.minute
    if 900 <= jam_pulang < 1380: return "SHIFT 1"
    if jam_pulang >= 1380 or jam_pulang < 420: return "SHIFT 2"
    return "SHIFT 3"

def hitung_jam_kerja(masuk_str, pulang_str):
    fmt = '%d/%m/%Y %H:%M:%S'
    masuk = datetime.strptime(masuk_str, fmt)
    pulang = datetime.strptime(pulang_str, fmt)
    total_jam = (pulang - masuk).total_seconds() / 3600 - 1 # KURANGI 1 JAM ISTIRAHAT
    if total_jam < 0: total_jam = 0
    jam_kerja = 7.0 if total_jam >= 7 else total_jam # MAX 7 JAM
    return f"{int(jam_kerja)}:00:00", hitung_shift(masuk, pulang)

# 7. TOMBOL ABSEN
col1, col2 = st.columns(2)
all_data = ws_absen.get_all_values()

with col1:
    if st.button("Absen Masuk", use_container_width=True):
        if id_karyawan and nama:
            row = [f"'{id_karyawan}", datetime_str, "", nama, "", ""]
            ws_absen.append_row(row, value_input_option='USER_ENTERED')
            st.success(f"✅ Absen Masuk: {datetime_str}")

with col2:
    if st.button("Absen Pulang", use_container_width=True):
        if id_karyawan and nama:
            row_index = None
            for i in range(len(all_data)-1, 0, -1):
                row = all_data[i]
                if row[0].lstrip("'").lstrip('0') == id_cari and row[2] == "":
                    row_index = i + 1
                    break
            if row_index:
                jam_masuk = ws_absen.cell(row_index, 2).value
                ws_absen.update_cell(row_index, 3, datetime_str)
                jam_kerja, shift = hitung_jam_kerja(jam_masuk, datetime_str)
                ws_absen.update_cell(row_index, 5, jam_kerja)
                ws_absen.update_cell(row_index, 6, shift)
                st.success(f"✅ Absen Pulang: {datetime_str}")
                st.info(f"Shift: {shift} | Jam Kerja: {jam_kerja}")
            else:
                st.error("Belum absen masuk")
