import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="GAJI FINAL V3.1", layout="wide")
st.title("💰 GAJI FINAL - LOYALITAS BULANAN")

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
    if not absen.empty:
        absen['ID KARYAWAN'] = absen['ID KARYAWAN'].astype(str).str.zfill(8)
        absen['TANGGAL'] = pd.to_datetime(absen['TANGGAL'], errors='coerce')
    return db, absen

db_df, absen_df = load()

def to_float(x):
    try:
        # Khusus uang shift 2187,5 biar tetap 2187.5
        s = str(x).replace('Rp','').strip()
        # ganti koma jadi titik untuk desimal
        if ',' in s and '.' in s:
            s = s.replace('.','').replace(',','.')
        elif ',' in s:
            s = s.replace(',','.')
        if s == '' or s.lower() == 'nan': return 0
        return float(s)
    except: return 0

bulan = st.selectbox("Bulan", range(1,13), index=7)
tahun = st.number_input("Tahun", value=2026)

if st.button("🔍 HITUNG GAJI", type="primary", use_container_width=True):
    absen_bulan = absen_df[(absen_df['TANGGAL'].dt.month==bulan) & (absen_df['TANGGAL'].dt.year==tahun)].copy()
    for c in ['LEMBUR 1.5','LEMBUR 2.0']:
        if c in absen_bulan.columns:
            absen_bulan[c] = pd.to_numeric(absen_bulan[c].astype(str).str.replace(',','.'), errors='coerce').fillna(0)

    rekap = []
    for _, kar in db_df.iterrows():
        id_kar = kar['ID KARYAWAN']
        data_kar = absen_bulan[absen_bulan['ID KARYAWAN']==id_kar]
        if data_kar.empty: continue

        nama = kar['NAMA KARYAWAN']
        gaji_bulan = to_float(kar['GAJI BULAN'])
        uang_shift = to_float(kar['UANG SHIFT']) # TETAP 2187.5 TIDAK DIKALI
        uang_makan = to_float(kar['UANG MAKAN'])
        premi_hadir = to_float(kar['PREMI HADIR'])
        loyalitas = to_float(kar['LOYALITAS']) # PER BULAN

        hari_kerja = len(data_kar) # jumlah hadir
        hari_shift = data_kar['SHIFT'].astype(str).str.contains('S2|S3|LS', case=False, na=False).sum()

        total_shift = hari_shift * uang_shift
        total_makan = hari_kerja * uang_makan
        total_premi = premi_hadir if hari_kerja > 0 else 0
        total_loyalitas = loyalitas if hari_kerja > 0 else 0 # PER BULAN FLAT

        total_l15 = data_kar['LEMBUR 1.5'].sum() if 'LEMBUR 1.5' in data_kar.columns else 0
        total_l20 = data_kar['LEMBUR 2.0'].sum() if 'LEMBUR 2.0' in data_kar.columns else 0
        total_lembur = (total_l15 * gaji_bulan/173 * 1.5) + (total_l20 * gaji_bulan/173 * 2.0)

        total_gaji = gaji_bulan + total_premi + total_makan + total_loyalitas + total_shift + total_lembur

        rekap.append([id_kar, nama, hari_kerja, hari_shift, int(gaji_bulan), int(premi_hadir), int(uang_makan), int(total_makan), uang_shift, total_shift, int(loyalitas), int(total_lembur), int(total_gaji)])

    df = pd.DataFrame(rekap, columns=['ID','NAMA','HARI KERJA','HARI SHIFT','GAJI POKOK','PREMI HADIR','MAKAN/HARI','TOTAL MAKAN','SHIFT/HARI','TOTAL SHIFT','LOYALITAS (BULAN)','LEMBUR','TOTAL GAJI'])
    st.dataframe(df, use_container_width=True)

    # Contoh hitungan RACHMAT dari data mu min:
    # 13 hari kerja, 2 hari shift
    # 5.252.909 + 50.000 + (13*9500=123.500) + 3.500 + (2*2187.5=4.375) = 5.434.284
    st.success(f"RACHMAT 13 hari, 2 shift: 5.252.909 + 50.000 + {13*9500} + 3.500 + {2*2187.5} = Rp {5252909+50000+123500+3500+4375:,} (belum lembur)")
    st.session_state['df'] = df

if 'df' in st.session_state:
    if st.button("💾 SIMPAN KE DATA GAJI"):
        df = st.session_state['df']
        ws_gaji.clear()
        ws_gaji.update([df.columns.tolist()] + df.values.tolist())
        st.balloons()
        st.success("Berhasil disimpan!")
