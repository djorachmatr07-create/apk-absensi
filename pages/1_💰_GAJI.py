import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="GAJI LENGKAP", layout="wide")
st.title("💰 HITUNG GAJI LENGKAP V2")

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
    # Biar semua angka kebaca
    for col in db.columns:
        db[col] = db[col].astype(str)

    absen = pd.DataFrame(ws_absen.get_all_records())
    if not absen.empty:
        absen['ID KARYAWAN'] = absen['ID KARYAWAN'].astype(str).str.zfill(8)
        absen['TANGGAL'] = pd.to_datetime(absen['TANGGAL'], errors='coerce')
    return db, absen

db_df, absen_df = load()

def to_float(x):
    try:
        x = str(x).replace('Rp','').replace('.','').replace(',','.').strip()
        if x == '' or x.lower() == 'nan': return 0
        f = float(x)
        if f < 5000 and f!=0: f = f # biarin, nanti yg shift aja yg dikali
        return f
    except: return 0

bulan = st.selectbox("Bulan", range(1,13), index=7)
tahun = st.number_input("Tahun", value=2026)

# Setting premi & uang makan per hari kalau gak ada di DB
with st.expander("⚙️ Setting Jika di DATABASE kosong"):
    default_premi = st.number_input("Default Premi Hadir (jika hadir full)", value=150000)
    default_makan = st.number_input("Default Uang Makan / Hari", value=25000)

if st.button("🔍 HITUNG GAJI LENGKAP", type="primary", use_container_width=True):
    absen_bulan = absen_df[(absen_df['TANGGAL'].dt.month==bulan) & (absen_df['TANGGAL'].dt.year==tahun)].copy()
    for c in ['LEMBUR 1.5','LEMBUR 2.0']:
        if c in absen_bulan.columns:
            absen_bulan[c] = pd.to_numeric(absen_bulan[c].astype(str).str.replace(',','.'), errors='coerce').fillna(0)

    rekap = []
    for _, kar in db_df.iterrows():
        id_kar = kar['ID KARYAWAN']
        nama = kar.get('NAMA KARYAWAN','')

        data_kar = absen_bulan[absen_bulan['ID KARYAWAN']==id_kar]
        if data_kar.empty: continue

        # --- AMBIL DARI DATABASE ---
        gaji_pokok = to_float(kar.get('GAJI BULAN', kar.get('GAJI POKOK', 0)))
        uang_shift_hari = to_float(kar.get('UANG SHIFT', 0))
        if uang_shift_hari > 0 and uang_shift_hari < 5000: uang_shift_hari *= 10
        if uang_shift_hari == 0: uang_shift_hari = 21875

        premi_db = to_float(kar.get('PREMI HADIR', 0))
        makan_db = to_float(kar.get('UANG MAKAN', 0))

        # --- HITUNG HARI ---
        # Hari kerja = jumlah hadir (ada TANGGAL)
        hari_kerja = len(data_kar)
        # Hari shift = yang S2/S3/LS
        hari_shift = data_kar['SHIFT'].astype(str).str.contains('S2|S3|LS', case=False, na=False).sum()

        # --- HITUNG KOMPONEN ---
        total_shift = hari_shift * uang_shift_hari

        # Uang makan = hari_kerja * uang makan per hari
        uang_makan_per_hari = makan_db if makan_db!=0 else default_makan
        total_uang_makan = hari_kerja * uang_makan_per_hari

        # Premi hadir = dapat kalau hadir >= 22 hari (atau full) - kalau gak, 0
        # Kalau di DB ada nilainya, pakai logika hadir full
        premi_hadir_db = premi_db if premi_db!=0 else default_premi
        # Misal premi full kalau hari kerja >= 20
        total_premi = premi_hadir_db if hari_kerja >= 20 else 0

        # Lembur
        total_l15 = data_kar['LEMBUR 1.5'].sum() if 'LEMBUR 1.5' in data_kar.columns else 0
        total_l20 = data_kar['LEMBUR 2.0'].sum() if 'LEMBUR 2.0' in data_kar.columns else 0
        rate = gaji_pokok / 173 if gaji_pokok!=0 else 0
        total_lembur = (total_l15 * rate * 1.5) + (total_l20 * rate * 2.0)

        total_gaji = gaji_pokok + total_premi + total_uang_makan + total_shift + total_lembur

        rekap.append([
            id_kar, nama, int(gaji_pokok), int(hari_kerja), int(total_premi),
            int(total_uang_makan), int(total_shift), int(total_lembur), int(total_gaji),
            int(hari_shift), float(total_l15), float(total_l20)
        ])

    df = pd.DataFrame(rekap, columns=[
        'ID KARYAWAN','NAMA KARYAWAN','GAJI POKOK','HARI KERJA','PREMI HADIR','UANG MAKAN','UANG SHIFT','UANG LEMBUR','TOTAL GAJI',
        'HARI SHIFT','L1.5','L2.0'
    ])
    st.dataframe(df, use_container_width=True)
    st.session_state['df_lengkap'] = df

    # Ringkasan
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Total Gaji Pokok", f"Rp {df['GAJI POKOK'].sum():,.0f}")
    c2.metric("Total Premi", f"Rp {df['PREMI HADIR'].sum():,.0f}")
    c3.metric("Total Makan", f"Rp {df['UANG MAKAN'].sum():,.0f}")
    c4.metric("TOTAL SEMUA", f"Rp {df['TOTAL GAJI'].sum():,.0f}")

if 'df_lengkap' in st.session_state:
    if st.button("💾 SIMPAN KE DATA GAJI", type="primary"):
        df = st.session_state['df_lengkap']
        # Simpan sesuai urutan header di SS kamu: ID, NAMA, GAJI POKOK, HARI KERJA, PREMI HADIR, UANG MAKAN, UANG SHIFT, UANG LEMBUR, TOTAL GAJI
        df_simpan = df[['ID KARYAWAN','NAMA KARYAWAN','GAJI POKOK','HARI KERJA','PREMI HADIR','UANG MAKAN','UANG SHIFT','UANG LEMBUR','TOTAL GAJI']]
        ws_gaji.clear()
        ws_gaji.update([df_simpan.columns.tolist()] + df_simpan.astype(str).values.tolist())
        st.balloons()
        st.success(f"✅ Berhasil simpan {len(df_simpan)} karyawan ke DATA GAJI")
