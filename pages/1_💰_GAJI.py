import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide")
st.title("💰 GAJI V14 - AUTO DARI ABSEN")

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
    # Coba deteksi nama kolom biar fleksibel
    absen.columns = [c.upper().strip() for c in absen.columns]
    return db, absen

db_df, absen_df = load()

def to_float(x):
    try:
        return float(str(x).replace(',','.').replace('Rp','').strip())
    except:
        return 0

def get_col(df, names):
    for n in names:
        if n in df.columns:
            return n
    return None

bulan = st.selectbox("Bulan", range(1,13), index=6)
tahun = st.number_input("Tahun", value=2026)
id_pilih = st.selectbox("Pilih Karyawan", db_df['ID KARYAWAN'].tolist())

if st.button("🔍 HITUNG REAL DARI ABSEN", type="primary", use_container_width=True):
    absen_bulan = absen_df[(absen_df['TANGGAL'].dt.month==bulan) & (absen_df['TANGGAL'].dt.year==tahun)].copy()
    kar = db_df[db_df['ID KARYAWAN']==id_pilih].iloc[0]
    data_kar = absen_bulan[absen_bulan['ID KARYAWAN']==id_pilih].copy()

    # --- DETEKSI KOLOM ABSEN ---
    col_status = get_col(data_kar, ['STATUS', 'KET', 'KETERANGAN'])
    col_shift = get_col(data_kar, ['SHIFT', 'JAM KERJA'])
    col_lembur = get_col(data_kar, ['JAM LEMBUR', 'LEMBUR', 'TOTAL LEMBUR', 'JML LEMBUR'])
    col_telat = get_col(data_kar, ['TELAT', 'JAM TELAT', 'MENIT TELAT', 'LATE'])
    col_makan_lembur = get_col(data_kar, ['MAKAN LEMBUR', 'UANG MAKAN LEMBUR'])

    if data_kar.empty:
        st.warning("Data absen kosong bulan ini")
        hari_kerja = 0
        jam_lembur = 0
        hari_shift = 0
        hari_telat = 0
        hari_makan_lembur = 0
    else:
        # HARI KERJA = STATUS H (HADIR)
        if col_status:
            data_hadir = data_kar[data_kar[col_status].astype(str).str.upper().str.contains('H|MASUK', na=False)]
        else:
            data_hadir = data_kar
        hari_kerja = len(data_hadir.drop_duplicates('TANGGAL'))

        # TELAT
        if col_telat:
            hari_telat = data_kar[to_float(data_kar[col_telat]) > 0].shape[0] if data_kar[col_telat].dtype!= object else data_kar[data_kar[col_telat].astype(str)!= '0'].shape[0]
            # lebih akurat: hitung yang mengandung T
            if col_status:
                hari_telat = max(hari_telat, data_kar[data_kar[col_status].astype(str).str.upper().str.contains('T|TELAT', na=False)].shape[0])
        else:
            hari_telat = data_kar[data_kar[col_status].astype(str).str.upper() == 'T'].shape[0] if col_status else 0

        # SHIFT S2/S3/LS
        if col_shift:
            hari_shift = data_kar[data_kar[col_shift].astype(str).str.upper().str.contains('S2|S3|LS|SHIFT', na=False)].shape[0]
        else:
            hari_shift = 0

        # JAM LEMBUR
        if col_lembur:
            data_kar[col_lembur] = data_kar[col_lembur].apply(to_float)
            jam_lembur = data_kar[col_lembur].sum()
        else:
            jam_lembur = 0

        # MAKAN LEMBUR - biasanya kalau lembur > 2 jam
        if col_makan_lembur:
            hari_makan_lembur = data_kar[data_kar[col_makan_lembur].astype(str).str.upper()!= '0'].shape[0]
        else:
            hari_makan_lembur = data_kar[data_kar[col_lembur] >= 2].shape[0] if col_lembur else 0

    # AMBIL MASTER GAJI
    gaji_pokok = to_float(kar['GAJI BULAN'])
    u_makan = to_float(kar['UANG MAKAN'])
    u_transport = to_float(kar['UANG TRANSPORT']) if 'UANG TRANSPORT' in kar else 0
    u_shift_rate = to_float(kar['UANG SHIFT']) if 'UANG SHIFT' in kar else 2187.5
    premi_full = to_float(kar['PREMI HADIR'])
    loyal = to_float(kar['LOYALITAS'])
    rate_lembur = to_float(kar['TARIF LEMBUR']) if 'TARIF LEMBUR' in kar else 30000
    u_makan_lembur_rate = to_float(kar['UANG MAKAN LEMBUR']) if 'UANG MAKAN LEMBUR' in kar else 9500

    # HITUNGAN REAL
    total_makan = hari_kerja * u_makan
    total_transport = hari_kerja * u_transport
    total_lembur = jam_lembur * rate_lembur
    total_shift = hari_shift * u_shift_rate
    total_makan_lembur = hari_makan_lembur * u_makan_lembur_rate

    # PREMI HADIR - potong kalau telat (contoh: kalau telat 1, tetap 50rb sesuai foto)
    # Kalau telat 0 = full, kalau telat >3 = 0
    if hari_telat == 0:
        premi = premi_full
    elif hari_telat == 1:
        premi = 50000 # sesuai foto
    else:
        premi = max(0, premi_full - (hari_telat * 25000))

    # BPJS
    jkk = gaji_pokok * 0.0024
    jkm = gaji_pokok * 0.0030
    jht_prsh = gaji_pokok * 0.037
    jp_prsh = gaji_pokok * 0.02
    bpjs_prsh = gaji_pokok * 0.04
    jht_tk = gaji_pokok * 0.02
    jp_tk = gaji_pokok * 0.01
    bpjs_kar = gaji_pokok * 0.01

    total_bpjs_prsh = jkk + jkm + jht_prsh + jp_prsh + bpjs_prsh
    total_bpjs_kar = jht_tk + jp_tk + bpjs_kar
    total_potongan = total_bpjs_prsh + total_bpjs_kar
    total_pendapatan = gaji_pokok + premi + total_makan + total_transport + total_lembur + total_shift + total_makan_lembur + loyal + total_bpjs_prsh
    total_gaji = total_pendapatan - total_potongan

    slip = [
        ["PENDAPATAN", "", "", "POTONGAN", ""],
        ["Gaji", "", int(gaji_pokok), "JKK (0.24%)", int(jkk)],
        ["Premi Hadir", f"{hari_telat} Telat", int(premi), "JKM (0.30%)", int(jkm)],
        ["Uang Makan", f"{hari_kerja} Hari x {int(u_makan)}", int(total_makan), "JHT Perusahaan (3.7%)", int(jht_prsh)],
        ["Uang Transport", f"{hari_kerja} Hari x {int(u_transport)}", int(total_transport), "JP Perusahaan (2%)", int(jp_prsh)],
        ["Uang Lembur", f"{jam_lembur} Jam x {int(rate_lembur)}", int(total_lembur), "BPJS Kes Perusahaan (4%)", int(bpjs_prsh)],
        ["Uang Shift", f"{hari_shift} Hari x {int(u_shift_rate)}", int(total_shift), "JHT TK (2%)", int(jht_tk)],
        ["Uang Makan Lembur", f"{hari_makan_lembur} Hari x {int(u_makan_lembur_rate)}", int(total_makan_lembur), "JP TK (1%)", int(jp_tk)],
        ["Tunjangan Loyalitas", "", int(loyal), "BPJS Kes Karyawan (1%)", int(bpjs_kar)],
        ["JKK (0.24%)", "", int(jkk), "", ""],
        ["JKM (0.30%)", "", int(jkm), "", ""],
        ["JHT Perusahaan (3.7%)", "", int(jht_prsh), "", ""],
        ["JP Perusahaan (2%)", "", int(jp_prsh), "", ""],
        ["BPJS Kes Perusahaan (4%)", "", int(bpjs_prsh), "", ""],
        ["", "", "", "", ""],
        ["TOTAL PENDAPATAN", "", int(total_pendapatan), "TOTAL POTONGAN", int(total_potongan)],
        ["", "", "", "", ""],
        ["TOTAL GAJI", "", int(total_gaji), "", ""],
    ]

    df = pd.DataFrame(slip, columns=["PENDAPATAN (A)", "KET (B)", "JUMLAH (C)", "POTONGAN (D)", "JUMLAH (E)"])
    st.dataframe(df, use_container_width=True, height=700)
    st.session_state['df_final'] = df

    # Debug biar tau hitungannya bener dari absen
    with st.expander("🔍 Cek Data Absen Real"):
        st.write(f"Hari Kerja: {hari_kerja}, Telat: {hari_telat}, Shift: {hari_shift}, Jam Lembur: {jam_lembur}, Makan Lembur: {hari_makan_lembur}")
        st.dataframe(data_kar)

if 'df_final' in st.session_state:
    if st.button("💾 SIMPAN KE DATA GAJI", type="primary"):
        df = st.session_state['df_final']
        data_simpan = [df.columns.tolist()] + df.astype(str).values.tolist()
        ws_gaji.clear()
        ws_gaji.update("A1", data_simpan, value_input_option="USER_ENTERED")
        st.balloons()
        st.success("✅ BERHASIL SIMPAN REAL DARI ABSEN!")
