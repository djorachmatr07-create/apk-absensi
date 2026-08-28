import streamlit as st, gspread, pandas as pd
from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide")
st.title("💰 GAJI V7 - VERTIKAL FIX")

@st.cache_resource
def connect():
    scope = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(creds)
    sh = client.open("REKAP")
    return sh.worksheet("REKAP ABSENSI"), sh.worksheet("DATABASE KARYAWAN"), sh.worksheet("DATA GAJI"), sh

ws_absen, ws_db, ws_gaji, spreadsheet = connect()

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
    try: return float(str(x).replace(',','.'))
    except: return 0

def bikin_vertikal(ws):
    body = {
        "requests": [{
            "repeatCell": {
                "range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 30},
                "cell": {"userEnteredFormat": {"textFormat": {"bold": True}, "textRotation": {"angle": 90}, "horizontalAlignment": "CENTER"}},
                "fields": "userEnteredFormat(textFormat,textRotation,horizontalAlignment)"
            }
        },{
            "updateDimensionProperties": {
                "range": {"sheetId": ws.id, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
                "properties": {"pixelSize": 200},
                "fields": "pixelSize"
            }
        }]
    }
    spreadsheet.batch_update(body)

bulan = st.selectbox("Bulan", range(1,13), index=7)
tahun = st.number_input("Tahun", value=2026)

if st.button("🔍 HITUNG GAJI + BPJS", type="primary", use_container_width=True):
    absen_bulan = absen_df[(absen_df['TANGGAL'].dt.month==bulan) & (absen_df['TANGGAL'].dt.year==tahun)].copy()
    rekap=[]
    for _, kar in db_df.iterrows():
        id_kar = kar['ID KARYAWAN']
        data_kar = absen_bulan[absen_bulan['ID KARYAWAN']==id_kar]
        if data_kar.empty: continue
        data_hadir = data_kar[data_kar['STATUS'].astype(str).str.upper()=='H']
        data_unik = data_hadir.drop_duplicates('TANGGAL')
        hari_kerja = len(data_unik)
        hari_shift = data_unik['SHIFT'].astype(str).str.contains('S2|S3|LS', case=False, na=False).sum()
        gaji_pokok = to_float(kar['GAJI BULAN'])
        u_shift = to_float(kar['UANG SHIFT'])
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
        total_pendapatan = gaji_pokok + premi + loyal + total_makan + total_shift + jkk + jkm + jht_prsh + jp_prsh + bpjs_kes_prsh
        total_potongan = jht_tk + jp_tk + bpjs_kes_kar
        gaji_bersih = total_pendapatan - total_potongan
        rekap.append([id_kar, kar['NAMA KARYAWAN'], hari_kerja, hari_shift, int(gaji_pokok), int(premi), int(loyal), int(total_makan), int(total_shift), int(jkk), int(jkm), int(jht_prsh), int(jp_prsh), int(bpjs_kes_prsh), int(jht_tk), int(jp_tk), int(bpjs_kes_kar), int(total_potongan), int(total_pendapatan), int(gaji_bersih)])
    cols = ['ID','NAMA','HARI KERJA','HARI SHIFT','GAJI POKOK','PREMI HADIR','LOYALITAS','TOTAL MAKAN','TOTAL SHIFT','JKK (0.24%)','JKM (0.30%)','JHT Prsh (3.7%)','JP Prsh (2%)','BPJS Kes Prsh (4%)','JHT TK (2%)','JP TK (1%)','BPJS Kes Kar (1%)','TOTAL POTONGAN','TOTAL PENDAPATAN','GAJI BERSIH']
    df = pd.DataFrame(rekap, columns=cols)
    st.dataframe(df, use_container_width=True)
    st.session_state['df']=df

if 'df' in st.session_state:
    if st.button("💾 SIMPAN & BIKIN VERTIKAL", type="primary"):
        df=st.session_state['df']
        ws_gaji.clear()
        ws_gaji.update([df.columns.tolist()]+df.values.tolist())
        bikin_vertikal(ws_gaji)
        st.balloons()
        st.success("✅ BERHASIL! Header sekarang vertikal 90 derajat di Google Sheet!")
