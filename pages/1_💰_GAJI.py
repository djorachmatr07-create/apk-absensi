import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="GAJI HADIR ONLY", layout="wide")
st.title("💰 GAJI - HANYA HADIR")

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

def to_float(x):
    try:
        s = str(x).replace(',','.').strip()
        return float(s) if s.lower()!='nan' and s!='' else 0
    except: return 0

bulan = st.selectbox("Bulan", range(1,13), index=7)
tahun = st.number_input("Tahun", value=2026)

if st.button("🔍 HITUNG GAJI HADIR ONLY", type="primary", use_container_width=True):
    absen_bulan = absen_df[(absen_df['TANGGAL'].dt.month==bulan) & (absen_df['TANGGAL'].dt.year==tahun)].copy()
    
    # DEBUG
    d = absen_bulan[absen_bulan['ID KARYAWAN']=='01213027']
    st.write(f"DEBUG RACHMAT: Total baris {len(d)} | Baris H {len(d[d['STATUS'].astype(str).str.contains('H', na=False)])}")

    rekap = []
    for _, kar in db_df.iterrows():
        id_kar = kar['ID KARYAWAN']
        data_kar = absen_bulan[absen_bulan['ID KARYAWAN']==id_kar]
        if data_kar.empty: continue

        # FIX UTAMA: HANYA YANG STATUS HADIR
        # Filter yang STATUS mengandung H (H, H-S2, H-S3, dll) atau SHIFT mengandung H-
        data_hadir = data_kar[data_kar['STATUS'].astype(str).str.upper().str.contains('H', na=False)]
        if len(data_hadir) == 0: # kalau STATUS kosong, anggap hadir
            data_hadir = data_kar

        # Hitung tanggal unik yang hadir aja
        data_unik = data_hadir.drop_duplicates(subset=['TANGGAL'])
        hari_kerja = len(data_unik) # INI JUMLAH HADIR
        hari_shift = data_unik['SHIFT'].astype(str).str.contains('S2|S3|LS', case=False, na=False).sum()

        gaji_bulan = to_float(kar['GAJI BULAN'])
        uang_shift = to_float(kar['UANG SHIFT']) # 2187.5 tetap
        uang_makan = to_float(kar['UANG MAKAN'])
        premi_hadir = to_float(kar['PREMI HADIR'])
        loyalitas = to_float(kar['LOYALITAS'])

        total_shift = hari_shift * uang_shift
        total_makan = hari_kerja * uang_makan
        total_premi = premi_hadir if hari_kerja > 0 else 0
        total_loyalitas = loyalitas if hari_kerja > 0 else 0
        total_gaji = gaji_bulan + total_premi + total_makan + total_loyalitas + total_shift

        rekap.append([id_kar, kar['NAMA KARYAWAN'], hari_kerja, hari_shift, total_shift, total_makan, premi_hadir, loyalitas, total_gaji])

    df = pd.DataFrame(rekap, columns=['ID','NAMA','HARI KERJA (HADIR)','HARI SHIFT','TOTAL SHIFT','TOTAL MAKAN','PREMI','LOYALITAS','TOTAL GAJI'])
    st.dataframe(df, use_container_width=True)
    st.success(f"HARI KERJA = hanya yang STATUS H saja | Sekarang harusnya 2, bukan 13")
    st.session_state['df'] = df

if 'df' in st.session_state:
    if st.button("💾 SIMPAN"):
        df = st.session_state['df']
        ws_gaji.clear()
        ws_gaji.update([df.columns.tolist()] + df.values.tolist())
        st.success("Tersimpan!")
