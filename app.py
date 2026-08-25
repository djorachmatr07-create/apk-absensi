import streamlit as st
import gspread
import datetime
from oauth2client.service_account import ServiceAccountCredentials

st.title("📍 APK ABSENSI KARYAWAN")

try:
    creds_dict = st.secrets["gcp_service_account"]
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    
    SHEET_ID = "1ZNPyue3P6RIX6JXdQW_sFjI9Faq0bEIXBM8i49E_5qQ"
    sheet = client.open_by_key(SHEET_ID).worksheet("REKAP ABSENSI")
    
    st.success("✅ Konek ke Google Sheet Berhasil")
except Exception as e:
    st.error(f"Gagal konek: {e}")
    st.stop()

id_karyawan = st.text_input("Masukkan ID Karyawan")
col1, col2 = st.columns(2)

with col1:
    if st.button("Absen Masuk"):
        if id_karyawan:
            waktu = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            sheet.append_row([id_karyawan, waktu, "", "", "", "", "", ""])
            st.success(f"Absen Masuk Berhasil jam {waktu}")
        else:
            st.warning("Isi ID dulu")

with col2:
    if st.button("Absen Pulang"):
        if id_karyawan:
            waktu = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            # cari baris terakhir ID ini yg jam pulang masih kosong
            cells = sheet.findall(id_karyawan)
            if cells:
                last_row = cells[-1].row
                sheet.update_cell(last_row, 3, waktu) # kolom C = JAM PULANG
                st.success(f"Absen Pulang Berhasil jam {waktu}")
            else:
                st.error("ID belum absen masuk")
        else:
            st.warning("Isi ID dulu")
