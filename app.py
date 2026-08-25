import streamlit as st
import gspread
import datetime
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="APK ABSENSI")
st.title("📍 APK ABSENSI KARYAWAN")

# KONEK PAKE SECRETS
try:
    creds_dict = st.secrets["gcp_service_account"]
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sh = client.open("REKAP")
    ws_absen = sh.worksheet("REKAP") # ganti kalau nama sheet nya beda
    
    st.success("2. Konek ke Google Sheet Berhasil")
except Exception as e:
    st.error(f"Gagal konek: {e}")
    st.stop()

id_karyawan = st.text_input("3. Masukkan ID Karyawan")

if st.button("Absen Masuk"):
    if id_karyawan:
        waktu = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        # Masukkin ke kolom: A=ID, B=JAM MASUK, C dst kosong
        ws_absen.append_row([id_karyawan, waktu, "", ""])
        st.success(f"Absen Masuk Berhasil jam {waktu}")
    else:
        st.warning("ID Karyawan wajib diisi")
