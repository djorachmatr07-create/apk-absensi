import streamlit as st
import gspread
import datetime
from oauth2client.service_account import ServiceAccountCredentials

st.title("📍 APK ABSENSI KARYAWAN")

# KONEKSI KE GOOGLE SHEET
try:
    creds_dict = st.secrets["gcp_service_account"]
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open("REKAP").sheet1 # GANTI NAMA GOOGLE SHEET KAMU
    
except Exception as e:
    st.error(f"Gagal konek: {e}")
    st.stop() # ini penting biar berhenti kalau gagal

# FORM ABSEN
id_karyawan = st.text_input("Masukkan ID Karyawan")

if st.button("Absen Masuk"):
    if id_karyawan:
        waktu = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([id_karyawan, waktu, "Masuk"])
        st.success(f"Absen Masuk Berhasil jam {waktu}")
    else:
        st.warning("ID Karyawan wajib diisi")
