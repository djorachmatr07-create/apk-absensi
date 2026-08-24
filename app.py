import streamlit as st
import gspread
from datetime import datetime, time, timedelta
from oauth2client.service_account import ServiceAccountCredentials
import json

st.set_page_config(page_title="APK ABSENSI", layout="centered")
st.title("📍 APK ABSENSI KARYAWAN ⚡")

creds_dict = st.secrets["gcp_service_account"]

try:
    scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets', "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)

    sh = client.open("REKAP")
    ws_absen = sh.worksheet("REKAP ABSENSI")
    ws_db = sh.worksheet("DATABASE KARYAWAN")
    st.success("✅ Konek ke Google Sheet 'REKAP' berhasil!")

    data_db = ws_db.get_all_records()
    db_dict = {str(row['ID KARYAWAN']).lstrip('0'): row['NAMA'] for row in data_db}
    headers = ["ID KARYAWAN", "JAM MASUK", "JAM PULANG", "NAMA KARYAWAN", "JAM KERJA", "JAM LEMBUR", "SHIFT", "UANG SHIFT", "KEHADIRAN", "KETERANGAN"]
    if ws_absen.row_values(1)!= headers:
        ws_absen.update('A1:J1', [headers])

    def bulat_masuk(dt_obj):
        if dt_obj.minute > 0 or dt_obj.second > 0:
            return (dt_obj + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        return dt_obj.replace(minute=0, second=0, microsecond=0)
    def bulat_pulang(dt_obj):
        return dt_obj.replace(minute=0, second=0, microsecond=0)
    def hitung_lembur_multiplier(total_lembur_jam):
        jam_lembur_efektif = 0.0; sisa = total_lembur_jam; jam_ke = 1
        while sisa > 0:
            ambil = 1.0 if sisa >= 1 else sisa
            if jam_ke == 1: jam_lembur_efektif += ambil * 1.5
            else: jam_lembur_efektif += ambil * 2.0
            sisa -= ambil; jam_ke += 1
        return f"{jam_lembur_efektif:.2f}"
    def tentukan_shift(masuk_dt, pulang_dt, total_jam_float, lembur_jam, is_tukar_hari):
        if is_tukar_hari: return "TUKAR HARI 🔄"
        if masuk_dt.weekday() == 5:
            if lembur_jam > 0: return "SABTU FULL DAY 🚀"
            jam_masuk = masuk_dt.hour
            if 7 <= jam_masuk < 12: return "SHIFT1 07-12 ☀️"
            elif 12 <= jam_masuk < 17: return "SHIFT2 12-17 🌤️"
            elif 17 <= jam_masuk < 22: return "SHIFT3 17-22 🌙"
            else: return "SHIFT SABTU"
        if masuk_dt.weekday() == 6: return "MINGGU KERJA 💪"
        total_jam_bersih = total_jam_float - 1 if total_jam_float >= 8 else total_jam_float
        jam_masuk = masuk_dt.hour
        if 7 <= jam_masuk < 8 and total_jam_bersih >= 10: return "LONG SHIFT1 07-18 🔥"
        elif 19 <= jam_masuk < 20 and total_jam_bersih >= 10: return "LONG SHIFT2 19-07 🌃"
        jam_pulang = pulang_dt.hour; menit_pulang = pulang_dt.minute; total_menit_pulang = jam_pulang * 60 + menit_pulang
        if 900 <= total_menit_pulang < 1380: return "SHIFT 1 15-23 🌆"
        elif total_menit_pulang >= 1380 or total_menit_pulang < 420: return "SHIFT 2 23-07 🌌"
        else: return "SHIFT 3 07-15 ☀️"
    def hitung_uang_shift(shift):
        if "SHIFT2" in shift or "SHIFT 2" in shift or "SHIFT3" in shift or "SHIFT 3" in shift or "LONG SHIFT" in shift: return 2187.5
        else: return 0
    def hitung_jam(masuk_str, pulang_str, is_tukar_hari):
        if not masuk_str or not pulang_str: return "7:00:00", "0.00", "", 0, "", ""
        fmt = '%d/%m/%Y %H:%M:%S'; masuk = datetime.strptime(masuk_str, fmt); pulang = datetime.strptime(pulang_str, fmt)
        masuk_bulat = bulat_masuk(masuk); pulang_bulat = bulat_pulang(pulang)
        total_jam_float = (pulang_bulat - masuk_bulat).total_seconds() / 3600
        total_jam_bersih = total_jam_float - 1 if total_jam_float >= 8 else total_jam_float
        if total_jam_bersih < 0: total_jam_bersih = 0
        if is_tukar_hari:
            jam_kerja_normal = 7.0; jam_kerja_float = jam_kerja_normal if total_jam_bersih >= jam_kerja_normal else total_jam_bersih
            jam_kerja = f"{int(jam_kerja_float)}:00:00"; lembur_jam = total_jam_bersih - jam_kerja_normal
            if lembur_jam < 0: lembur_jam = 0; keterangan = "TUKAR HARI 🔄"
        elif masuk_bulat.weekday() == 6:
            jam_kerja = "7:00:00"; lembur_jam = total_jam_bersih; keterangan = "MASUK ✅"
        elif masuk_bulat.weekday() == 5:
            jam_kerja_normal = 5.0; jam_kerja_float = jam_kerja_normal if total_jam_bersih >= jam_kerja_normal else total_jam_bersih
            jam_kerja = f"{int(jam_kerja_float)}:00:00"; lembur_jam = total_jam_bersih - jam_kerja_normal
            if lembur_jam < 0: lembur_jam = 0; keterangan = "MASUK ✅"
        else:
            jam_kerja_normal = 7.0; jam_kerja_float = jam_kerja_normal if total_jam_bersih >= jam_kerja_normal else total_jam_bersih
            jam_kerja = f"{int(jam_kerja_float)}:00:00"; lembur_jam = total_jam_bersih - jam_kerja_normal
            if lembur_jam < 0: lembur_jam = 0; keterangan = "MASUK ✅"
        if masuk_bulat.weekday() == 6: lembur_multiplier = f"{total_jam_bersih * 2:.2f}"
        else: lembur_multiplier = hitung_lembur_multiplier(lembur_jam)
        shift_final = tentukan_shift(masuk_bulat, pulang_bulat, total_jam_float, lembur_jam, is_tukar_hari)
        uang_shift = hitung_uang_shift(shift_final); kehadiran = 1
        return jam_kerja, lembur_multiplier, shift_final, uang_shift, kehadiran, keterangan

    id_karyawan = st.text_input("🆔 3. ID KARYAWAN")
    nama = ""
    if id_karyawan:
        id_cari = id_karyawan.lstrip('0'); nama = db_dict.get(id_cari, "")
        if nama: st.text_input("👤 4. NAMA KARYAWAN", value=nama, disabled=True)
        else: st.error("ID tidak ada di database")
    all_data = ws_absen.get_all_values(); st.markdown("---")
    opsi_jam = st.radio("⏰ Pilih Waktu Absen:", ["⚡ Gunakan Jam Sekarang", "🛠️ Pilih Jam Manual"], horizontal=True)
    if opsi_jam == "⚡ Gunakan Jam Sekarang": waktu_absen = datetime.now()
    else:
        tanggal = st.date_input("📅 Tanggal"); jam = st.time_input("🕐 Jam")
        waktu_absen = datetime.combine(tanggal, jam)
    status_hari = st.radio("📋 Status Hari Ini:", ["📅 Hari Normal", "🔄 Tukar Hari / Pengganti"], horizontal=True)
    datetime_str = waktu_absen.strftime('%d/%m/%Y %H:%M:%S')
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🟢 ABSEN MASUK", use_container_width=True):
            if id_karyawan and nama:
                tanggal_cari = waktu_absen.strftime('%d/%m/%Y'); row_index = None
                for i, row in enumerate(all_data[1:], start=2):
                    if row[0].lstrip("'").lstrip('0') == id_cari and row[1].startswith(tanggal_cari): row_index = i; break
                if row_index: ws_absen.update_cell(row_index, 2, datetime_str)
                else: ws_absen.append_row([f"'{id_karyawan}", datetime_str, "", nama, "", ""], value_input_option='USER_ENTERED')
                st.success(f"✅ Absen Masuk jam {waktu_absen.strftime('%H:%M:%S')}")
            else: st.warning("⚠️ Isi ID yang benar dulu")
    with col2:
        if st.button("🔴 ABSEN PULANG", use_container_width=True):
            if id_karyawan and nama:
                row_index = None
                for i in range(len(all_data)-1, 0, -1):
                    row = all_data[i]
                    if row[0].lstrip("'").lstrip('0') == id_cari and row[2] == "": row_index = i + 1; break
                if row_index:
                    jam_masuk = ws_absen.cell(row_index, 2).value; ws_absen.update_cell(row_index, 3, datetime_str)
                    is_tukar = True if status_hari == "🔄 Tukar Hari / Pengganti" else False
                    jam_kerja, jam_lembur, shift_final, uang_shift, kehadiran, keterangan = hitung_jam(jam_masuk, datetime_str, is_tukar)
                    ws_absen.update_cell(row_index, 5, jam_kerja); ws_absen.update_cell(row_index, 6, jam_lembur)
                    ws_absen.update_cell(row_index, 7, shift_final); ws_absen.update_cell(row_index, 8, uang_shift)
                    ws_absen.update_cell(row_index, 9, kehadiran); ws_absen.update_cell(row_index, 10, keterangan)
                    st.success("✅ Absen Pulang berhasil!")
                    st.info(f"🎯 {shift_final} | ⏱️ {jam_kerja} | 💰 {jam_lembur} Jam | 💵 {uang_shift}")
                else: st.error("❌ Tidak ada data absen masuk yg belum pulang")
            else: st.warning("⚠️ Isi ID yang benar dulu")
except Exception as e:
    st.error(f"Gagal konek: {e}")
