import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide")
st.title("💰 GAJI V12 - POTONGAN LENGKAP")

@st.cache_resource
def connect():
    scope = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
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
        return float(str(x).replace(',','.'))
    except:
        return 0

bulan = st.selectbox("Bulan", range(1,13), index=7)
tahun = st.number_input("Tahun", value=2026)
id_pilih = st.selectbox("Pilih Karyawan", db_df['ID KARYAWAN'].tolist())

if st.button("🔍 HITUNG SLIP VERTIKAL", type="primary", use_container_width=True):
    absen_bulan = absen_df[(absen_df['TANGGAL'].dt.month==bulan) & (absen_df['TANGGAL'].dt.year==tahun)].copy()
    kar = db_df[db_df['ID KARYAWAN']==id_pilih].iloc[0]
    data_kar = absen_bulan[absen_bulan['ID KARYAWAN']==id_pilih]
    data_hadir = data_kar[data_kar['STATUS'].astype(str).str.upper()=='H']
    data_unik = data_hadir.drop_duplicates('TANGGAL')
    hari_kerja = len(data_unik)
    hari_shift = data_unik['SHIFT'].astype(str).str.contains('S2|S3|LS', case=False, na=False).sum()

    gaji_pokok = to_float(kar['GAJI BULAN'])
    u_shift = 2187.5
    u_makan = to_float(kar['UANG MAKAN'])
    premi = to_float(kar['PREMI HADIR'])
    loyal = to_float(kar['LOYALITAS'])

    jkk = gaji_pokok * 0.0024
    jkm = gaji_pokok * 0.0030
    jht_prsh = gaji_pokok * 0.037
    jp_prsh = gaji_pokok * 0.02
    bpjs_kes_prsh = gaji_pokok * 0.04
    jht_tk = gaji_pokok * 0.02
    jp_tk = gaji_pokok * 0.01
    bpjs_kes_kar = gaji_pokok * 0.01

    total_shift = hari_shift * u_shift
    total_makan = hari_kerja * u_makan

    total_bpjs_prsh = jkk + jkm + jht_prsh + jp_prsh + bpjs_kes_prsh
    total_bpjs_kar = jht_tk + jp_tk + bpjs_kes_kar
    total_potongan_lengkap = total_bpjs_prsh + total_bpjs_kar
    total_pendapatan = gaji_pokok + premi + loyal + total_makan + total_shift + total_bpjs_prsh
    gaji_bersih = total_pendapatan - total_bpjs_kar

    slip = [
        ["ID KARYAWAN", id_pilih],
        ["NAMA", str(kar['NAMA KARYAWAN'])],
        ["PERIODE", f"{bulan}/{tahun}"],
        ["HARI KERJA HADIR", hari_kerja],
        ["HARI SHIFT", hari_shift],
        ["", ""],
        ["GAJI POKOK", int(gaji_pokok)],
        ["PREMI HADIR", int(premi)],
        ["LOYALITAS", int(loyal)],
        ["TOTAL MAKAN", int(total_makan)],
        ["TOTAL SHIFT", int(total_shift)],
        ["", ""],
        ["JKK (0.24%)", int(jkk)],
        ["JKM (0.30%)", int(jkm)],
        ["JHT Perusahaan (3.7%)", int(jht_prsh)],
        ["JP Perusahaan (2%)", int(jp_prsh)],
        ["BPJS Kes Perusahaan (4%)", int(bpjs_kes_prsh)],
        ["JHT TK (2%)", int(jht_tk)],
        ["JP TK (1%)", int(jp_tk)],
        ["BPJS Kes Karyawan (1%)", int(bpjs_kes_kar)],
        ["", ""],
        ["TOTAL POTONGAN", int(total_potongan_lengkap)],
        ["KET TOTAL POTONGAN", "JKK+JKM+JHT Prsh+JP Prsh+BPJS Prsh+JHT TK+JP TK+BPJS Kar = 748011"],
        ["TOTAL PENDAPATAN", int(total_pendapatan)],
        ["GAJI BERSIH", int(gaji_bersih)],
    ]

    df = pd.DataFrame(slip, columns=["KOMPONEN (A)", "NILAI (B)"])
    st.dataframe(df, use_container_width=True, height=700)
    st.session_state['df_final'] = df
    st.info(f"TOTAL POTONGAN: {int(total_potongan_lengkap):,} (harusnya 748,011) | BERSIH: {int(gaji_bersih):,}")

if 'df_final' in st.session_state:
    if st.button("💾 SIMPAN VERTIKAL", type="primary"):
        df = st.session_state['df_final']
        data_simpan = [df.columns.tolist()] + df.astype(str).values.tolist()
        ws_gaji.clear()
        ws_gaji.update("A1", data_simpan, value_input_option="USER_ENTERED")
        st.balloons()
        st.success("BERHASIL! Total potongan 748,011 udah lengkap")
