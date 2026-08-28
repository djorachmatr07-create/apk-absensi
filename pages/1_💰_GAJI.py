import streamlit as st, gspread, pandas as pd
from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide")
st.title("💰 GAJI FINAL V5 - BPJS % GAJI POKOK")

# CSS HEADER VERTIKAL BIAR DI HP KELIATAN SEMUA
st.markdown("""
<style>
thead th {
    writing-mode: vertical-rl !important;
    transform: rotate(180deg);
    white-space: nowrap;
    height: 180px !important;
    vertical-align: bottom !important;
    text-align: left !important;
}
[data-testid="stDataFrame"] { width: 100%; }
</style>
""", unsafe_allow_html=True)

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
    try: return float(str(x).replace(',','.'))
    except: return 0

bulan = st.selectbox("Bulan", range(1,13), index=7)
tahun = st.number_input("Tahun", value=2026)

if st.button("🔍 HITUNG GAJI + BPJS", type="primary", use_container_width=True):
    absen_bulan = absen_df[(absen_df['TANGGAL'].dt.month==bulan) & (absen_df['TANGGAL'].dt.year==tahun)].copy()

    rekap=[]
    for _, kar in db_df.iterrows():
        id_kar = kar['ID KARYAWAN']
        data_kar = absen_bulan[absen_bulan['ID KARYAWAN']==id_kar]
        if data_kar.empty: continue

        # HARI KERJA = HADIR ONLY + TANGGAL UNIK
        data_hadir = data_kar[data_kar['STATUS'].astype(str).str.upper()=='H']
        data_unik = data_hadir.drop_duplicates('TANGGAL')
        hari_kerja = len(data_unik)
        hari_shift = data_unik['SHIFT'].astype(str).str.contains('S2|S3|LS', case=False, na=False).sum()

        gaji_pokok = to_float(kar['GAJI BULAN'])
        u_shift = to_float(kar['UANG SHIFT']) # 2187.5 tetap
        u_makan = to_float(kar['UANG MAKAN'])
        premi = to_float(kar['PREMI HADIR'])
        loyal = to_float(kar['LOYALITAS'])

        # --- HITUNG % DARI GAJI POKOK (SESUAI SS MU) ---
        jkk = gaji_pokok * 0.0024
        jkm = gaji_pokok * 0.0030
        jht_perusahaan = gaji_pokok * 0.037
        jp_perusahaan = gaji_pokok * 0.02
        bpjs_kes_perusahaan = gaji_pokok * 0.04

        jht_tk = gaji_pokok * 0.02
        jp_tk = gaji_pokok * 0.01
        bpjs_kes_karyawan = gaji_pokok * 0.01

        total_shift = hari_shift * u_shift
        total_makan = hari_kerja * u_makan

        total_pendapatan = gaji_pokok + premi + loyal + total_makan + total_shift + jkk + jkm + jht_perusahaan + jp_perusahaan + bpjs_kes_perusahaan
        total_potongan = jht_tk + jp_tk + bpjs_kes_karyawan
        gaji_bersih = total_pendapatan - total_potongan

        rekap.append([
            id_kar, kar['NAMA KARYAWAN'], hari_kerja, hari_shift,
            int(gaji_pokok), int(premi), int(loyal), int(total_makan), int(total_shift),
            int(jkk), int(jkm), int(jht_perusahaan), int(jp_perusahaan), int(bpjs_kes_perusahaan),
            int(jht_tk), int(jp_tk), int(bpjs_kes_karyawan),
            int(total_potongan), int(total_pendapatan), int(gaji_bersih)
        ])

    cols = ['ID','NAMA','HARI KERJA','HARI SHIFT','GAJI POKOK','PREMI HADIR','LOYALITAS','TOTAL MAKAN','TOTAL SHIFT',
            'JKK (0.24%)','JKM (0.30%)','JHT Perusahaan (3.7%)','JP Perusahaan (2%)','BPJS Kes Perusahaan (4%)',
            'JHT TK (2%)','JP TK (1%)','BPJS Kes Karyawan (1%)','TOTAL POTONGAN','TOTAL PENDAPATAN','GAJI BERSIH']

    df = pd.DataFrame(rekap, columns=cols)
    st.dataframe(df, use_container_width=True, height=600)
    st.session_state['df']=df

    # Contoh hitungan sesuai SS
    st.success(f"RACHMAT contoh: Gaji 5.252.909 -> JKK {5252909*0.0024:,.0f} | JKM {5252909*0.003:,.0f} | JHT Prsh {5252909*0.037:,.0f} | Total Potongan {5252909*0.04:,.0f}")

if 'df' in st.session_state:
    if st.button("💾 SIMPAN KE DATA GAJI"):
        df=st.session_state['df']
        ws_gaji.clear()
        ws_gaji.update([df.columns.tolist()]+df.values.tolist())
        st.balloons()
        st.success("Berhasil! Header udah vertikal jadi keliatan semua di HP")
