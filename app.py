import streamlit as st
import gspread
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="APK ABSENSI", layout="centered")
st.title("📍 APK ABSENSI KARYAWAN")

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

data_db = ws_db.get_all_records()
db_dict = {str(row['ID KARYAWAN']).lstrip('0'): row['NAMA'] for row in data_db}

headers = ["ID KARYAWAN", "JAM MASUK", "JAM PULANG", "NAMA KARYAWAN", "JAM KERJA", "JAM LEMBUR", "SHIFT"]
if ws_absen.row_values(1)!= headers:
    ws_absen.update('A1:G1', [headers])

id_karyawan = st.text_input("1. Masukkan ID Karyawan")
nama = ""
if id_karyawan:
    id_cari = id_karyawan.lstrip('0')
    nama = db_dict.get(id_cari, "")
    if nama:
        st.text_input("2. Nama Karyawan", value=nama, disabled=True)
    else:
        st.error("ID tidak ditemukan di DATABASE KARYAWAN")

st.markdown("---")
# PILIHAN GANTI HARI
opsi_jam = st.radio("3. Waktu Absen:", ["Jam Sekarang", "Pilih Hari & Jam Manual"], horizontal=True)
if opsi_jam == "Jam Sekarang":
    waktu_absen = datetime.now()
else:
    tanggal = st.date_input("Pilih Tanggal")
    jam = st.time_input("Pilih Jam")
    waktu_absen = datetime.combine(tanggal, jam)

datetime_str = waktu_absen.strftime('%d/%m/%Y %H:%M:%S')
st.text_input("4. SHIFT OTOMATIS", value="Akan ditentukan saat pulang", disabled=True)

def bulat_masuk(dt_obj):
    if dt_obj.minute > 0 or dt_obj.second > 0:
        return (dt_obj + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    return dt_obj.replace(minute=0, second=0, microsecond=0)

def bulat_pulang(dt_obj):
    return dt_obj.replace(minute=0, second=0, microsecond=0)

def hitung_lembur_multiplier(total_lembur_jam):
    jam_lembur_efektif = 0.0
    sisa = total_lembur_jam
    jam_ke = 1
    while sisa > 0:
        ambil = 1.0 if sisa >= 1 else sisa
        if jam_ke == 1:
            jam_lembur_efektif += ambil * 1.5 # K1 x 1.5
        else:
            jam_lembur_efektif += ambil * 2.0 # K2 dst x 2
        sisa -= ambil
        jam_ke += 1
    return f"{jam_lembur_efektif:.2f}"

def tentukan_shift(masuk_dt, pulang_dt):
    total_jam_mentah = (pulang_dt - masuk_dt).total_seconds() / 3600
    total_jam_bersih = total_jam_mentah - 1 # -1 jam istirahat
    jam_masuk = masuk_dt.hour
    
    if 7 <= jam_masuk < 8 and total_jam_bersih >= 10:
        return "LONG SHIFT1 07-18"
    elif 19 <= jam_masuk < 20 and total_jam_bersih >= 10:
        return "LONG SHIFT2 19-07"
    
    jam_pulang = pulang_dt.hour
    menit_pulang = pulang_dt.minute
    total_menit_pulang = jam_pulang * 60 + menit_pulang
    
    if 900 <= total_menit_pulang < 1380:
        return "SHIFT 1"
    elif total_menit_pulang >= 1380 or total_menit_pulang < 420:
        return "SHIFT 2"
    else:
        return "SHIFT 3"

def hitung_jam(masuk_str, pulang_str):
    if not masuk_str or not pulang_str:
        return "7:00:00", "0.00", ""
    fmt = '%d/%m/%Y %H:%M:%S'
    masuk = datetime.strptime(masuk_str, fmt)
    pulang = datetime.strptime(pulang_str, fmt)
    
    masuk_bulat = bulat_masuk(masuk)
    pulang_bulat = bulat_pulang(pulang)
    
    total_jam_mentah = pulang_bulat - masuk_bulat
    total_jam_bersih = total_jam_mentah - timedelta(hours=1) # KURANGI 1 JAM ISTIRAHAT
    total_jam_float = total_jam_bersih.total_seconds() / 3600
    if total_jam_float < 0: total_jam_float = 0
    
    # CEK APAKAH SABTU
    jam_efektif = 5.0 if masuk.weekday() == 5 else 7.0 # 5=Sabtu, 6=Minggu
    
    jam_kerja_float = jam_efektif if total_jam_float >= jam_efektif else total_jam_float
    lembur_jam = total_jam_float - jam_efektif
    if lembur_jam < 0: lembur_jam = 0
    
    jam_kerja = f"{int(jam_kerja_float)}:00:00"
    lembur_multiplier = hitung_lembur_multiplier(lembur_jam)
    shift_final = tentukan_shift(masuk_bulat, pulang_bulat)
    return jam_kerja, lembur_multiplier, shift_final

col1, col2 = st.columns(2)
all_data = ws_absen.get_all_values()

with col1:
    if st.button("ABSEN MASUK", use_container_width=True):
        if id_karyawan and nama:
            row = [f"'{id_karyawan}", datetime_str, "", nama, "", "0.00", ""]
            ws_absen.append_row(row, value_input_option='USER_ENTERED')
            st.success(f"✅ Absen Masuk: {datetime_str}")
        else:
            st.warning("Isi ID yang benar dulu min")

with col2:
    if st.button("ABSEN PULANG", use_container_width=True):
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
                jam_kerja, jam_lembur, shift = hitung_jam(jam_masuk, datetime_str)
                ws_absen.update_cell(row_index, 5, jam_kerja)
                ws_absen.update_cell(row_index, 6, jam_lembur)
                ws_absen.update_cell(row_index, 7, shift)
                st.success(f"✅ Absen Pulang: {datetime_str}")
                st.info(f"Shift: {shift} | Kerja: {jam_kerja} | Lembur: {jam_lembur} Jam")
            else:
                st.error("Tidak ada data absen masuk yg belum pulang")
        else:
            st.warning("Isi ID yang benar dulu min")
