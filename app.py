import streamlit as st
import gspread
import datetime
from oauth2client.service_account import ServiceAccountCredentials

st.title("📍 APK ABSENSI KARYAWAN")

try:
    creds_dict = st.secrets["gcp_service_account"]
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open("REKAP").worksheet("REKAP") # INI YG DIGANTI
    st.success("✅ Konek ke Google Sheet Berhasil")
except Exception as e:
    st.error(f"Gagal konek: {e}")
    st.stop()

id_karyawan = st.text_input("Masukkan ID Karyawan")
if st.button("Absen Masuk"):
    if id_karyawan:
        waktu = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        sheet.append_row([id_karyawan, waktu, "", "", "", "", ""])
        st.success(f"Absen Masuk Berhasil jam {waktu}")
