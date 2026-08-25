import streamlit as st
import gspread
import requests
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="APK ABSENSI", layout="centered")
st.title("📍 APK ABSENSI KARYAWAN")

PASSWORD_ADMIN = "admin123" # GANTI PASSWORD KAMU DISINI MIN

# 1. KONEK KE SHEET
@st.cache_resource
def connect_gsheet():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(creds)
    sh = client.open("REKAP")
    ws_absen = sh.worksheet("REKAP ABSENSI")
    ws_db = sh.worksheet("DATABASE KARYAWAN")
    ws_db.format('A:A', {'numberFormat': {'type': 'TEXT'}})
    ws_absen.format('A:A', {'numberFormat': {'type': 'TEXT'}})
    ws_absen.format('B:C', {'numberFormat': {'type': 'DATE_TIME', 'pattern': 'dd/mm/yyyy hh:mm:ss'}})
    return ws_absen, ws_db

ws_absen, ws_db = connect_gsheet()
st.success("✅ Konek ke Google Sheet Berhasil")

# 2. AMBIL DATA LIBUR NASIONAL
@st.cache_data(ttl=86400)
def get_libur_nasional(tahun):
    try:
        url = f"https://indonesia-holiday-api.vercel.app/api/{tahun}"
        res = requests.get(url, timeout=5)
        data = res.json()
        set_libur = {item['holiday_date'] for item in data}
        return set_libur
    except:
        return set()

# 3. BACA DATABASE
@st.cache_data(ttl=300)
def load_db():
    data_db = ws_db.get_all_records()
    return {str(row['ID KARYAWAN']).strip(): row['NAMA'] for row in data_db}

db_dict = load_db()

# 4. PASTIIN HEADER
headers = ["ID KARYAWAN", "JAM MASUK", "JAM PULANG", "NAMA KARYAWAN", "JAM KERJA", "JAM LEMBUR", "SHIFT", "KETERANGAN"]
if ws_absen.row_values(1)!= headers:
    ws_absen.update('A1:H1', [headers])

def sort_by_tanggal():
    ws_absen.sort((2, 'des'))

# 5. FUNGSI AUTO LIBUR MINGGU 23:59
def auto_libur_minggu():
    all_data = ws_absen.get_all_values()
    karyawan_ids = list(db_dict.keys())
    hari_ini = datetime.now()
    for i in range(7):
        tgl_cek = hari_ini - timedelta(days=i)
        if tgl_cek.weekday() == 6:
            tgl_str = tgl_cek.strftime('%d/%m/%Y')
            jam_23_59 = tgl_cek.replace(hour=23, minute=59, second=0).strftime('%d/%m/%Y %H:%M:%S')
            for id_kar in karyawan_ids:
                sudah_absen = False
                for row in all_data[1:]:
                    if str(row[0]).strip() == id_kar and row[1]:
                        tgl_db = datetime.strptime(row[1], '%d/%m/%Y %H:%M:%S').strftime('%d/%m/%Y')
                        if tgl_db == tgl_str: sudah_absen = True; break
                if not sudah_absen:
                    row_baru = [id_kar, jam_23_59, jam_23_59, db_dict[id_kar], "0:00:00", "0.00", "LIBUR", "LIBUR OTOMATIS"]
                    ws_absen.insert_row(row_baru, 2, value_input_option='RAW')
    sort_by_tanggal()
    st.cache_data.clear()

auto_libur_minggu()

# 6. CEK PASSWORD ADMIN DULU
if "admin_login" not in st.session_state:
    st.session_state.admin_login = False

menu = st.tabs(["📝 ABSEN", "✏️ EDIT DATA"])

with menu[1]: # TAB EDIT DATA DIKUNCI
    if not st.session_state.admin_login:
        st.warning("⚠️ Area Admin. Masukkan password untuk akses edit data")
        pass_input = st.text_input("Password Admin", type="password", key="pass")
        if st.button("LOGIN"):
            if pass_input == PASSWORD_ADMIN:
                st.session_state.admin_login = True
                st.rerun()
            else:
                st.error("Password salah min")
    else:
        st.success("✅ Login Admin Berhasil")
        if st.button("LOGOUT"):
            st.session_state.admin_login = False
            st.rerun()

        st.markdown("---")
        id_edit = st.text_input("Masukkan ID Karyawan yg mau diedit", key="id_edit").strip()

        if id_edit:
            all_data = ws_absen.get_all_values()
            data_karyawan = [row for row in all_data[1:] if str(row[0]).strip() == id_edit]

            if data_karyawan:
                opsi_data = []
                for i, row in enumerate(data_karyawan[:10]):
                    opsi_data.append(f"{row[1]} s/d {row[2]} - {row[7]}")

                pilih = st.selectbox("Pilih data yg mau diedit:", opsi_data, key="pilih_edit")
                row_index_asli = all_data.index(data_karyawan[opsi_data.index(pilih)]) + 1

                col1, col2 = st.columns(2)
                with col1:
                    jam_masuk_lama = datetime.strptime(ws_absen.cell(row_index_asli, 2).value, '%d/%m/%Y %H:%M:%S')
                    jam_masuk_baru_tgl = st.date_input("Tanggal Masuk Baru", jam_masuk_lama.date(), key="edit_tgl_masuk")
                    jam_masuk_baru_jam = st.time_input("Jam Masuk Baru", jam_masuk_lama.time(), key="edit_jam_masuk")

                with col2:
                    jam_pulang_lama = datetime.strptime(ws_absen.cell(row_index_asli, 3).value, '%d/%m/%Y %H:%M:%S')
                    jam_pulang_baru_tgl = st.date_input("Tanggal Pulang Baru", jam_pulang_lama.date(), key="edit_tgl_pulang")
                    jam_pulang_baru_jam = st.time_input("Jam Pulang Baru", jam_pulang_lama.time(), key="edit_jam_pulang")

                status_baru = st.selectbox("Status Hari Baru", ["NORMAL", "TUKAR HARI", "LIBUR"], key="status_edit")

                if st.button("💾 SIMPAN PERUBAHAN", use_container_width=True):
                    jam_masuk_baru = datetime.combine(jam_masuk_baru_tgl, jam_masuk_baru_jam).strftime('%d/%m/%Y %H:%M:%S')
                    jam_pulang_baru = datetime.combine(jam_pulang_baru_tgl, jam_pulang_baru_jam).strftime('%d/%m/%Y %H:%M:%S')
                    set_libur = get_libur_nasional(jam_masuk_baru_tgl.year)

                    ws_absen.update_cell(row_index_asli, 2, jam_masuk_baru)
                    ws_absen.update_cell(row_index_asli, 3, jam_pulang_baru)

                    # FUNGSI HITUNG COPY DARI TAB ABSEN
                    def bulat_masuk(dt_obj):
                        if dt_obj.minute > 0 or dt_obj.second > 0:
                            return (dt_obj + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
                        return dt_obj.replace(minute=0, second=0, microsecond=0)
                    def bulat_pulang(dt_obj): return dt_obj.replace(minute=0, second=0, microsecond=0)
                    def hitung_lembur_multiplier(total_lembur_jam, multiplier=2.0): return f"{total_lembur_jam * multiplier:.2f}"
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
                        fmt = '%d/%m/%Y %H:%M:%S'; masuk = datetime.strptime(masuk_str, fmt); pulang = datetime.strptime(pulang_str, fmt)
                        masuk_bulat = bulat_masuk(masuk); pulang_bulat = bulat_pulang(pulang)
                        total_jam_mentah = (pulang_bulat - masuk_bulat).total_seconds() / 3600
                        tanggal_api_format = masuk.strftime('%Y-%m-%d'); weekday = masuk.weekday()
                        is_libur_api = (weekday == 6) or (tanggal_api_format in set_libur)
                        is_libur = False; keterangan = ""
                        if status_hari == "LIBUR": is_libur = True; keterangan = "LEMBUR"
                        elif status_hari == "TUKAR HARI": is_libur = False; keterangan = "TUKAR HARI"
                        else:
                            is_libur = is_libur_api
                            if is_libur: keterangan = "LEMBUR"
                            elif weekday == 5: keterangan = "SABTU"
                            else: keterangan = "HARI KERJA"
                        jam_kerja_float = 0.0; lembur_jam = 0.0; lembur_multiplier = "0.00"
                        if is_libur:
                            total_jam_bersih = total_jam_mentah - 1;
                            if total_jam_bersih < 0: total_jam_bersih = 0
                            jam_kerja_float = 0.0; lembur_jam = total_jam_bersih
                            lembur_multiplier = hitung_lembur_multiplier(lembur_jam, 2.0)
                        elif weekday == 5 and status_hari == "NORMAL":
                            total_jam_bersih = total_jam_mentah; jam_efektif = 5.0
                            if total_jam_bersih >= 8.0: total_jam_bersih -= 1.0; keterangan = "SABTU FULL DAY"
                            lembur_jam = total_jam_bersih - jam_efektif
                            if lembur_jam < 0: lembur_jam = 0
                            jam_kerja_float = jam_efektif if total_jam_bersih >= jam_efektif else total_jam_bersih
                            if lembur_jam > 0:
                                jam_pertama = 1.0 if lembur_jam >= 1 else lembur_jam; sisa = lembur_jam - jam_pertama
                                lembur_efektif = (jam_pertama * 1.5) + (sisa * 2.0); lembur_multiplier = f"{lembur_efektif:.2f}"
                        else:
                            total_jam_bersih = total_jam_mentah - 1;
                            if total_jam_bersih < 0: total_jam_bersih = 0
                            jam_efektif = 7.0; lembur_jam = total_jam_bersih - jam_efektif
                            if lembur_jam < 0: lembur_jam = 0
                            jam_kerja_float = jam_efektif if total_jam_bersih >= jam_efektif else total_jam_bersih
                            if lembur_jam > 0:
                                jam_pertama = 1.0 if lembur_jam >= 1 else lembur_jam; sisa = lembur_jam - jam_pertama
                                lembur_efektif = (jam_pertama * 1.5) + (sisa * 2.0); lembur_multiplier = f"{lembur_efektif:.2f}"
                        jam_kerja = f"{int(jam_kerja_float)}:00:00"; shift_final = tentukan_shift(masuk_bulat, pulang_bulat)
                        return jam_kerja, lembur_multiplier, shift_final, keterangan

                    jam_kerja, jam_lembur, shift, ket = hitung_jam(jam_masuk_baru, jam_pulang_baru, set_libur, status_baru)
                    ws_absen.update_cell(row_index_asli, 5, jam_kerja); ws_absen.update_cell(row_index_asli, 6, jam_lembur)
                    ws_absen.update_cell(row_index_asli, 7, shift); ws_absen.update_cell(row_index_asli, 8, ket)
                    sort_by_tanggal()
                    st.success("✅ Data berhasil diedit dan dihitung ulang!")
                    st.cache_data.clear()
            else:
                st.error("ID tidak ditemukan di REKAP ABSENSI")

with menu[0]: # TAB ABSEN TETAP BISA DIAKSES SEMUA
    id_karyawan = st.text_input("1. Masukkan ID Karyawan", key="id_absen").strip()
    nama = ""
    if id_karyawan:
        nama = db_dict.get(id_karyawan, "")
        if nama:
            st.text_input("2. Nama Karyawan", value=nama, disabled=True, key="nama_absen")
        else:
            st.error(f"ID '{id_karyawan}' tidak ditemukan di DATABASE KARYAWAN")

    st.markdown("---")
    opsi_jam = st.radio("3. Waktu Absen:", ["Jam Sekarang", "Pilih Hari & Jam Manual"], horizontal=True, key="opsi")
    if opsi_jam == "Jam Sekarang":
        waktu_absen = datetime.now()
    else:
        col_tgl, col_jam = st.columns(2)
        with col_tgl: tanggal = st.date_input("Pilih Tanggal", value=datetime.now().date(), key="tgl")
        with col_jam: jam = st.time_input("Pilih Jam", value=datetime.now().time(), key="jam")
        waktu_absen = datetime.combine(tanggal, jam)

    status_hari = st.selectbox("4. Status Hari", ["NORMAL", "TUKAR HARI", "LIBUR"], key="status")
    st.text_input("5. SHIFT OTOMATIS", value="Akan ditentukan saat pulang", disabled=True)
    set_libur = get_libur_nasional(waktu_absen.year)

    #... SISA KODE ABSEN MASUK/PULANG SAMA KAYAK SEBELUMNYA...
    # Tinggal copy fungsi hitung_jam dll dari atas
