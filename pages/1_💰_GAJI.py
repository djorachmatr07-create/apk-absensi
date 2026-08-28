import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="GAJI", layout="wide")
st.title("💰 GAJI - HARI = HADIR")

@st.cache_resource
def connect():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(creds)
    sh = client.open("REKAP")
    return sh.worksheet("REKAP ABSENSI"), sh.worksheet("DATABASE KARYAWAN"), sh.worksheet("DATA GAJI")

ws_absen, ws_db, ws_gaji = connect()

@st.cache_data(ttl=60)
def load():
    db = pd.DataFrame(ws_db.get_all_records())
    db['ID KARYAWAN'] = db['ID KARYAWAN'].astype(str).str.zfill(8)
    absen = pd.DataFrame(ws_absen.get_all_records())
    absen['ID KARYAWAN'] = absen['ID KARYAWAN'].astype(str).str.zfill(8)
    absen['TANGGAL'] = pd.to_datetime(absen['TANGGAL'], errors='coerce')
    return db, absen

db_df, absen_df = load()

bulan = st.selectbox("Bulan", range(1,13), index=7)
tahun = st.number_input("Tahun", value=2026)

if st.button("🔍 HITUNG GAJI", type="primary", use_container_width=True):
    absen_bulan = absen_df[(absen_df['TANGGAL'].dt.month==bulan) & (absen_df['TANGGAL'].dt.year==tahun)].copy()
    for c in ['LEMBUR 1.5','LEMBUR 2.0']:
        absen_bulan[c] = pd.to_numeric(absen_bulan[c].astype(str).str.replace(',','.'), errors='coerce').fillna(0)

    rekap = []
    for id_kar in db_df['ID KARYAWAN'].unique():
        data_kar = absen_bulan[absen_bulan['ID KARYAWAN']==id_kar]
        if data_kar.empty: continue
        nama = db_df[db_df['ID KARYAWAN']==id_kar]['NAMA KARYAWAN'].values[0]
        try:
            gaji_bulan = float(str(db_df[db_df['ID KARYAWAN']==id_kar]['GAJI BULAN'].values[0]).replace('.','').replace(',','.'))
        except: gaji_bulan = 5252909
        try:
            u = str(db_df[db_df['ID KARYAWAN']==id_kar]['UANG SHIFT'].values[0]).replace('.','').replace(',','.')
            uang_hari = float(u)
            if uang_hari < 5000: uang_hari *= 10
        except: uang_hari = 21875

        # FIX UTAMA DI SINI MIN
        hari_kerja = len(data_kar) # JUMLAH HADIR
        hari_shift = data_kar['SHIFT'].astype(str).str.contains('S2|S3|LS', case=False, na=False).sum()
        total_shift = hari_shift * uang_hari

        total_l15 = data_kar['LEMBUR 1.5'].sum()
        total_l20 = data_kar['LEMBUR 2.0'].sum()
        total_lembur = (total_l15 * gaji_bulan/173 * 1.5) + (total_l20 * gaji_bulan/173 * 2.0)

        rekap.append([id_kar, nama, hari_kerja, hari_shift, uang_hari, total_shift, total_l15, total_l20, total_lembur])

    df = pd.DataFrame(rekap, columns=['ID','NAMA','HARI KERJA (HADIR)','HARI SHIFT','UANG/HARI','TOTAL SHIFT','L1.5','L2.0','TOTAL LEMBUR'])
    st.dataframe(df, use_container_width=True)
    st.session_state['df'] = df
    st.success(f"Hari Kerja dihitung dari HADIR | Total Shift Rp {df['TOTAL SHIFT'].sum():,.0f}")

if 'df' in st.session_state:
    if st.button("💾 SIMPAN KE DATA GAJI"):
        df = st.session_state['df']
        ws_gaji.clear()
        ws_gaji.update([df.columns.tolist()] + df.astype(str).values.tolist())
        st.balloons()
        st.success("Berhasil!")
