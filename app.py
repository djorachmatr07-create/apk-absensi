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
    
    # Biar kita tau file apa aja yg bisa diakses
    files = client.list_spreadsheet_files()
    st.write("File yg kebaca:", [f['name'] for f in files])
    
    sheet = client.open("REKAP").sheet1
    
except Exception as e:
    st.error(f"Gagal konek: {e}")
    st.stop()
