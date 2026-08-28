import streamlit as st, gspread, pandas as pd
from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide")
st.title("💰 GAJI V8 - SLIP VERTIKAL")

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

# Pilih karyawan biar enak dilihat di HP
id_pilih = st.selectbox("Pilih Karyawan (untuk lihat vertikal)", db_df['ID KARYAWAN'].tolist())

if st.button("🔍 HITUNG SLIP VERTIKAL", type="primary", use_container_width=True):
    absen_bulan = absen_df[(absen_df['TANGGAL'].dt.month==bulan) & (absen_df['TANGGAL'].dt.year==tahun)].copy()

    kar = db_df[db_df['ID KARYAWAN']==id_pilih].iloc[0]
    data_kar = absen_bulan[absen_bulan['ID KARYAWAN']==id_pilih]

    data_hadir = data_kar[data_kar['STATUS'].astype(str).str.upper()=='H']
    data_unik = data_hadir.drop_duplicates('TANGGAL')
    hari_kerja = len(data_unik)
    hari_shift = data_unik['SHIFT'].astype(str).str.contains('S2|S3|LS', case=False, na=False).sum()

    gaji_pokok = to_float(kar['GAJI BULAN'])
    u_shift = to_float(kar['UANG SHIFT']) # 2187.5 tetap
    u_makan = to_float(kar['UANG MAKAN'])
    premi = to_float(kar['PREMI HADIR'])
    loyal = to_float(kar['LOYALITAS'])

    # % BPJS
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

    # BIKIN FORMAT VERTIKAL A=HEADER, B=DETAIL
    slip_vertikal = [
        ["ID KARYAWAN", id_pilih],
        ["NAMA KARYAWAN", kar['NAMA KARYAWAN']],
        ["BULAN/TAHUN", f"{bulan}/{tahun}"],
        ["---", "---"],
        ["HARI KERJA (HADIR)", hari_kerja],
        ["HARI SHIFT", hari_shift],
        ["---", "---"],
        ["GAJI POKOK", int(gaji_pokok)],
        ["PREMI HADIR", int(premi)],
        ["LOYALITAS (BULAN)", int(loyal)],
        ["UANG MAKAN / HARI", int(u_makan)],
        ["TOTAL UANG MAKAN", int(total_makan)],
        ["UANG SHIFT / HARI", u_shift],
        ["TOTAL UANG SHIFT", total_shift],
        ["---", "---"],
        ["JKK (0.24%)", int(jkk)],
        ["JKM (0.30%)", int(jkm)],
        ["JHT Perusahaan (3.7%)", int(jht_prsh)],
        ["JP Perusahaan (2%)", int(jp_prsh)],
        ["BPJS Kes Perusahaan (4%)", int(bpjs_kes_prsh)],
        ["---", "---"],
        ["JHT TK (2%)", int(jht_tk)],
        ["JP TK (1%)", int(jp_tk)],
        ["BPJS Kes Karyawan (1%)", int(bpjs_kes_kar)],
        ["TOTAL POTONGAN", int(total_potongan)],
        ["---", "---"],
        ["TOTAL PENDAPATAN", int(total_pendapatan)],
        ["GAJI BERSIH", int(gaji_bersih)],
    ]

    df_vertikal = pd.DataFrame(slip_vertikal, columns=["KOMPONEN", "NILAI"])
    st.dataframe(df_vertikal, use_container_width=True, height=800)
    st.session_state['df_vertikal'] = df_vertikal

    # Contoh semua karyawan versi horizontal vertikal (A=komponen, B,C,D = karyawan)
    st.divider()
    st.write("Rekap Semua Karyawan (Kolom A = Komponen):")
    # Buat rekap semua biar tetap kesimpan

if 'df_vertikal' in st.session_state:
    if st.button("💾 SIMPAN VERTIKAL KE DATA GAJI", type="primary"):
        df = st.session_state['df_vertikal']
        ws_gaji.clear()
        ws_gaji.update([df.columns.tolist()] + df.values.tolist())
        ws_gaji.format("A1:B1", {"textFormat": {"bold": True}})
        ws_gaji.format("A:A", {"textFormat": {"bold": True}})
        st.balloons()
        st.success("✅ BERHASIL! Sekarang di Google Sheet DATA GAJI: Kolom A = Header, Kolom B = Detail. Cek HP sekarang min, udah enak dilihat!")
