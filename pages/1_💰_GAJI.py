import streamlit as st, gspread, pandas as pd
from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide")
st.title("💰 GAJI V6 - HEADER VERTIKAL AUTO")

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

# FUNGSI BIKIN HEADER VERTIKAL DI GOOGLE SHEET
def bikin_vertikal(ws):
    try:
        body = {
            "requests": [{
                "repeatCell": {
                    "range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": 1},
                    "cell": {"textFormat": {"bold": True, "fontSize": 10}, "textRotation": {"angle": 90}},
                    "fields": "textFormat, textRotation"
                }
            },{
                "updateSheetProperties": {
                    "properties": {"sheetId": ws.id, "gridProperties": {"frozenRowCount": 1}},
                    "fields": "gridProperties.frozenRowCount"
                }
            }]
        }
        spreadsheet.batch_update(body)
        # Tinggi header
        ws_gaji.format("A1:Z1", {"textFormat": {"bold": True}})
        return True
    except Exception as e:
        st.warning(f"Gagal auto vertikal: {e} -> coba manual ya min: blok baris 1 > Format > Rotasi teks > Putar 90 derajat")
        return False

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
        u_shift = to_float(kar['UANG SHIFT']) # 2187.5 tetap
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
        st.success("✅ Disimpan & Header udah vertikal! Coba buka Google Sheet DATA GAJI sekarang min, headernya udah berdiri.")
        st.info("Kalau masih horizontal: buka Sheet > blok baris 1 > Format > Rotasi teks > 90 derajat (manual 1x aja)")
