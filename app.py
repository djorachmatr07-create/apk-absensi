import streamlit as st
import gspread
import requests
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="APK ABSENSI", layout="wide")
st.title("📍 APK ABSENSI KARYAWAN")

PASSWORD_ADMIN = "admin123"

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
st.success("🛜 Konek ke Google Sheet Berhasil")

@st.cache_data(ttl=86400)
def get_libur_nasional(tahun):
    try:
        url = f"https://indonesia-holiday-api.vercel.app/api/{tahun}"
        res = requests.get(url, timeout=5)
        data = res.json()
        dict_libur = {item['holiday_date']: item['holiday_name'] for item in data}
        return dict_libur
    except:
        return {}

@st.cache_data(ttl=300)
def load_db():
    all_values = ws_db.get_all_values()
    db = {}
    for row in all_values[1:]:
        id_kar_raw = str(row[0]).strip()
        id_kar = id_kar_raw.zfill(8) # GANTI 8 SESUAI PANJANG ID
        nama = str(row[1]).strip()
        db[id_kar] = nama
    return db

db_dict = load_db()

headers = ["ID KARYAWAN", "JAM MASUK", "JAM PULANG", "NAMA KARYAWAN", "JAM KERJA", "JAM LEMBUR", "SHIFT", "KETERANGAN"]
if ws_absen.row_values(1)!= headers:
    ws_absen.update('A1:H1', [headers])

def sort_by_tanggal():
    try: ws_absen.sort((2, 'des'))
    except: pass

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

def hitung_jam(masuk_str, pulang_str, dict_libur, status_hari):
    if not masuk_str or not pulang_str: return "0:00:00", "0.00", "", ""
    fmt = '%d/%m/%Y %H:%M:%S'; masuk = datetime.strptime(masuk_str, fmt); pulang = datetime.strptime(pulang_str, fmt)
    masuk_bulat = bulat_masuk(masuk); pulang_bulat = bulat_pulang(pulang)
    total_jam_mentah = (pulang_bulat - masuk_bulat).total_seconds() / 3600
    tanggal_api_format = masuk.strftime('%Y-%m-%d'); weekday = masuk.weekday()
    nama_libur = dict_libur.get(tanggal_api_format, "")
    is_libur_api = (weekday == 6) or (tanggal_api_format in dict_libur)
    is_libur = False; keterangan = ""
    if status_hari == "LIBUR":
        is_libur = True
        keterangan = f"LEMBUR {nama_libur}" if nama_libur else "LEMBUR"
    elif status_hari == "TUKAR HARI":
        is_libur = False; keterangan = "TUKAR HARI"
    else:
        if nama_libur: is_libur = True; keterangan = nama_libur
        elif weekday == 6: is_libur = True; keterangan = "LIBUR MINGGU"
        elif weekday == 5: is_libur = False; keterangan = "SABTU"
        else: is_libur = False; keterangan = "HARI KERJA"

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

def sudah_absen_masuk(id_kar, tanggal_str, all_data):
    id_kar = id_kar.zfill(8)
    for row in all_data[1:]:
        if str(row[0]).strip().zfill(8) == id_kar and row[1]:
            tgl_db = datetime.strptime(row[1], '%d/%m/%Y %H:%M:%S').strftime('%d/%m/%Y')
            if tgl_db == tanggal_str: return True
    return False
def cari_data_belum_pulang(id_kar, all_data):
    id_kar = id_kar.zfill(8)
    for i in range(len(all_data)-1, 0, -1):
        row = all_data[i]
        if str(row[0]).strip().zfill(8) == id_kar and row[2] == "": return i + 1
    return None

# FIX UTAMA: AUTO ALPA + AUTO LIBUR
def auto_absen_23_59():
    all_data = ws_absen.get_all_values()
    karyawan_ids = list(db_dict.keys())
    hari_ini = datetime.now()
    dict_libur = get_libur_nasional(hari_ini.year)

    for i in range(14): # cek 14 hari kebelakang
        tgl_cek = hari_ini - timedelta(days=i)
        tgl_str = tgl_cek.strftime('%d/%m/%Y')
        tgl_api = tgl_cek.strftime('%Y-%m-%d')
        jam_23_59 = tgl_cek.replace(hour=23, minute=59, second=0).strftime('%d/%m/%Y %H:%M:%S')

        nama_libur = dict_libur.get(tgl_api, "")
        is_minggu = tgl_cek.weekday() == 6
        is_tgl_merah = tgl_api in dict_libur
        is_hari_kerja = not is_minggu and not is_tgl_merah

        for id_kar in karyawan_ids:
            sudah_absen = False
            for row in all_data[1:]:
                if str(row[0]).strip().zfill(8) == id_kar and row[1]:
                    tgl_db = datetime.strptime(row[1], '%d/%m/%Y %H:%M:%S').strftime('%d/%m/%Y')
                    if tgl_db == tgl_str: sudah_absen = True; break

            if not sudah_absen:
                if is_tgl_merah:
                    keterangan = f"LIBUR NASIONAL: {nama_libur}"
                elif is_minggu:
                    keterangan = "LIBUR MINGGU OTOMATIS"
                elif is_hari_kerja: # SENIN - SABTU BUKAN LIBUR
                    keterangan = "ALPA"
                else:
                    continue # skip

                row_baru = [id_kar, jam_23_59, jam_23_59, db_dict[id_kar], "0:00:00", "0.00", "ALPA" if is_hari_kerja else "LIBUR", keterangan]
                ws_absen.insert_row(row_baru, 2, value_input_option='RAW')
    sort_by_tanggal(); st.cache_data.clear()

auto_absen_23_59()

if "admin_login" not in st.session_state: st.session_state.admin_login = False
menu = st.tabs(["📝 ABSEN", "✏️ EDIT DATA"])

with menu[1]:
    if not st.session_state.admin_login:
        st.warning("⚠️ Area Admin")
        pass_input = st.text_input("Password Admin", type="password", key="pass")
        if st.button("LOGIN"):
            if pass_input == PASSWORD_ADMIN: st.session_state.admin_login = True; st.rerun()
            else: st.error("Password salah min")
    else:
        st.success("✅ Login Admin Berhasil")
        if st.button("LOGOUT"): st.session_state.admin_login = False; st.rerun()
        st.markdown("---")
        id_edit = st.text_input("Masukkan ID Karyawan yg mau diedit", key="id_edit").strip().zfill(8)
        if id_edit:
            all_data = ws_absen.get_all_values()
            data_karyawan = [row for row in all_data[1:] if str(row[0]).strip().zfill(8) == id_edit]
            if data_karyawan:
                opsi_data = [f"{row[1]} s/d {row[2]} - {row[7]}" for row in data_karyawan[:10]]
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
                    dict_libur = get_libur_nasional(jam_masuk_baru_tgl.year)
                    ws_absen.update_cell(row_index_asli, 2, jam_masuk_baru)
                    ws_absen.update_cell(row_index_asli, 3, jam_pulang_baru)
                    jam_kerja, jam_lembur, shift, ket = hitung_jam(jam_masuk_baru, jam_pulang_baru, dict_libur, status_baru)
                    ws_absen.update_cell(row_index_asli, 5, jam_kerja); ws_absen.update_cell(row_index_asli, 6, jam_lembur)
                    ws_absen.update_cell(row_index_asli, 7, shift); ws_absen.update_cell(row_index_asli, 8, ket)
                    sort_by_tanggal(); st.success("✅ Data berhasil diedit!"); st.cache_data.clear()
            else: st.error("ID tidak ditemukan di REKAP ABSENSI")

with menu[0]:
    id_karyawan_raw = st.text_input("1. Masukkan ID Karyawan", key="id_absen").strip()
    id_karyawan = id_karyawan_raw.zfill(8)
    nama = ""
    if id_karyawan_raw:
        nama = db_dict.get(id_karyawan, "")
        if nama: st.text_input("2. Nama Karyawan", value=nama, disabled=True, key="nama_absen")
        else: st.error(f"ID '{id_karyawan}' tidak ditemukan di DATABASE KARYAWAN")

    st.markdown("---")
    opsi_jam = st.radio("3. Waktu Absen:", ["Jam Sekarang", "Pilih Hari & Jam Manual"], horizontal=True, key="opsi")
    if opsi_jam == "Jam Sekarang": waktu_absen = datetime.now()
    else:
        col_tgl, col_jam = st.columns(2)
        with col_tgl: tanggal = st.date_input("Pilih Tanggal", value=datetime.now().date(), key="tgl")
        with col_jam: jam = st.time_input("Pilih Jam", value=datetime.now().time(), key="jam")
        waktu_absen = datetime.combine(tanggal, jam)

    status_hari = st.selectbox("4. Status Hari", ["NORMAL", "TUKAR HARI", "LIBUR"], key="status")
    st.text_input("5. SHIFT OTOMATIS", value="Akan ditentukan saat pulang", disabled=True)
    dict_libur = get_libur_nasional(waktu_absen.year)

    col1, col2, col3, col4 = st.columns(4)
    all_data = ws_absen.get_all_values()
    tanggal_hari_ini = waktu_absen.strftime('%d/%m/%Y')

    with col1:
        if st.button("ABSEN MASUK", use_container_width=True):
            if id_karyawan_raw and nama:
                if sudah_absen_masuk(id_karyawan, tanggal_hari_ini, all_data): st.error(f"❌ Gagal! {nama} sudah absen masuk di tanggal {tanggal_hari_ini}")
                else:
                    datetime_str = waktu_absen.strftime('%d/%m/%Y %H:%M:%S')
                    row = [id_karyawan, datetime_str, "", nama, "", "0.00", "", ""]
                    ws_absen.insert_row(row, 2, value_input_option='RAW'); sort_by_tanggal()
                    st.success(f"✅ Absen Masuk: {datetime_str}"); st.cache_data.clear()
            else: st.warning("Isi ID yang benar dulu min")

    with col2:
        if st.button("ABSEN PULANG", use_container_width=True):
            if id_karyawan_raw and nama:
                row_index = cari_data_belum_pulang(id_karyawan, all_data)
                if row_index:
                    datetime_str = waktu_absen.strftime('%d/%m/%Y %H:%M:%S')
                    jam_masuk = ws_absen.cell(row_index, 2).value
                    ws_absen.update_cell(row_index, 3, datetime_str)
                    jam_kerja, jam_lembur, shift, ket = hitung_jam(jam_masuk, datetime_str, dict_libur, status_hari)
                    ws_absen.update_cell(row_index, 5, jam_kerja); ws_absen.update_cell(row_index, 6, jam_lembur)
                    ws_absen.update_cell(row_index, 7, shift); ws_absen.update_cell(row_index, 8, ket)
                    sort_by_tanggal()
                    st.success(f"✅ Absen Pulang: {datetime_str}")
                    st.info(f"Shift: {shift} | Kerja: {jam_kerja} | Lembur: {jam_lembur} Jam | {ket}"); st.cache_data.clear()
                else: st.error("❌ Tidak ada data absen masuk yg belum pulang")
            else: st.warning("Isi ID yang benar dulu min")

    with col3:
        if st.button("🔄 RECALCULATE", use_container_width=True):
            if id_karyawan_raw and nama:
                for i in range(len(all_data)-1, 0, -1):
                    if str(all_data[i][0]).strip().zfill(8) == id_karyawan and all_data[i][2]!= "":
                        row_index = i + 1; jam_masuk = ws_absen.cell(row_index, 2).value; jam_pulang = ws_absen.cell(row_index, 3).value
                        jam_kerja, jam_lembur, shift, ket = hitung_jam(jam_masuk, jam_pulang, dict_libur, status_hari)
                        ws_absen.update_cell(row_index, 5, jam_kerja); ws_absen.update_cell(row_index, 6, jam_lembur)
                        ws_absen.update_cell(row_index, 7, shift); ws_absen.update_cell(row_index, 8, ket)
                        sort_by_tanggal()
                        st.success(f"✅ Data {jam_masuk} berhasil dihitung ulang"); st.cache_data.clear(); break
                else: st.error("Data tidak ditemukan")
            else: st.warning("Isi ID yang benar dulu min")

    with col4:
        if st.button("⛪ CEK LIBUR/ALPA", use_container_width=True):
            auto_absen_23_59(); st.success("✅ Cek Libur & Alpa otomatis selesai")
