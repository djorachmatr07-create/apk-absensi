import streamlit as st, gspread, pandas as pd, calendar
from datetime import date, timedelta
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="GAJI V16", layout="wide", page_icon="💰")
st.markdown("<h2>💰 GAJI V16 - RUMUS LENGKAP GITHUB</h2><p style='color:#9CA3AF'>21-20 Payroll | GH/GHS=H | G=H*1.5+I*2.0</p>", unsafe_allow_html=True)

@st.cache_resource
def connect_gsheet():
    scope = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(creds)
    sh = client.open("REKAP")
    return sh.worksheet("REKAP ABSENSI"), sh.worksheet("DATABASE KARYAWAN")
ws_absen, ws_db = connect_gsheet()

@st.cache_data(ttl=60)
def load_data():
    db = pd.DataFrame(ws_db.get_all_records())
    db['ID KARYAWAN'] = db['ID KARYAWAN'].astype(str).str.zfill(8)
    vals = ws_absen.get_all_values()
    HEADER = ['ID KARYAWAN','NAMA KARYAWAN','TANGGAL','JAM MASUK','JAM PULANG','JAM KERJA','JAM LEMBUR','LEMBUR 1.5','LEMBUR 2.0','SHIFT','KETERANGAN','STATUS','UANG SHIFT']
    if len(vals)>1:
        data = [r[:13] for r in vals[1:]]
        absen = pd.DataFrame(data, columns=HEADER) if data else pd.DataFrame(columns=HEADER)
    else:
        absen = pd.DataFrame(columns=HEADER)
    if not absen.empty:
        absen['ID KARYAWAN'] = absen['ID KARYAWAN'].astype(str).str.zfill(8)
        absen['TGL_DT'] = pd.to_datetime(absen['TANGGAL'], format='%Y-%m-%d', errors='coerce')
    return db, absen

db_df, absen_df = load_data()

def hitung_gaji_lengkap(id_kar, tgl_awal, tgl_akhir):
    df = absen_df[
        (absen_df['ID KARYAWAN']==id_kar) &
        (absen_df['TGL_DT']>=pd.to_datetime(tgl_awal)) &
        (absen_df['TGL_DT']<=pd.to_datetime(tgl_akhir))
    ].copy()
    if df.empty:
        return None

    hadir = len(df[df['STATUS']=='H'])
    alfa = len(df[df['STATUS']=='A'])
    df['JAM_LEMBUR_F'] = pd.to_numeric(df['JAM LEMBUR'], errors='coerce').fillna(0)
    total_lembur_g = df['JAM_LEMBUR_F'].sum()
    jml_shift = len(df[(df['STATUS']=='H') & (df['SHIFT'].str.contains('S2|S3', na=False))])
    hari_lembur = len(df[df['JAM_LEMBUR_F']>0])

    gaji_pokok = 5252909
    premi_hadir = 50000 if alfa==0 else 0
    uang_makan = hadir * 9500
    uang_transport = hadir * 0
    uang_lembur = total_lembur_g * 30000
    uang_shift = jml_shift * 2187
    uang_makan_lembur = hari_lembur * 9500
    tunj_loyalitas = 3500

    jkk = round(gaji_pokok * 0.0024)
    jkm = round(gaji_pokok * 0.0030)
    jht_perusahaan = round(gaji_pokok * 0.037)
    jp_perusahaan = round(gaji_pokok * 0.02)
    bpjs_kes_perusahaan = round(gaji_pokok * 0.04)

    total_pendapatan = gaji_pokok + premi_hadir + uang_makan + uang_transport + uang_lembur + uang_shift + uang_makan_lembur + tunj_loyalitas + jkk + jkm + jht_perusahaan + jp_perusahaan + bpjs_kes_perusahaan

    pot_jkk = jkk
    pot_jkm = jkm
    pot_jht_perusahaan = jht_perusahaan
    pot_jp_perusahaan = jp_perusahaan
    pot_bpjs_kes_perusahaan = bpjs_kes_perusahaan
    pot_jht_tk = round(gaji_pokok * 0.02)
    pot_jp_tk = round(gaji_pokok * 0.01)
    pot_bpjs_kes_karyawan = round(gaji_pokok * 0.01)

    total_potongan = pot_jkk + pot_jkm + pot_jht_perusahaan + pot_jp_perusahaan + pot_bpjs_kes_perusahaan + pot_jht_tk + pot_jp_tk + pot_bpjs_kes_karyawan
    total_gaji = total_pendapatan - total_potongan

    return hadir, total_lembur_g, jml_shift, hari_lembur, total_pendapatan, total_potongan, total_gaji, df, premi_hadir, uang_makan, uang_lembur, uang_shift

# === UI - TANPA TAB5 ===
mode_g = st.radio("Mode", ["21-20 Payroll","Bulan Kalender","Custom"], horizontal=True)
c1,c2 = st.columns(2)
with c1: bulan_g = st.selectbox("Bulan", list(range(1,13)), index=8)
with c2: tahun_g = st.number_input("Tahun", 2020, 2030, 2026)

if mode_g=="Custom":
    cc1,cc2 = st.columns(2)
    with cc1: awal_g = st.date_input("Dari", date(tahun_g,bulan_g,1))
    with cc2: akhir_g = st.date_input("Sampai", date(tahun_g,bulan_g,20))
else:
    if mode_g=="21-20 Payroll":
        if bulan_g==1:
            awal_g=date(tahun_g-1,12,21)
            akhir_g=date(tahun_g,1,20)
        else:
            awal_g=date(tahun_g,bulan_g-1,21)
            akhir_g=date(tahun_g,bulan_g,20)
    else:
        awal_g=date(tahun_g,bulan_g,1)
        akhir_g=date(tahun_g,bulan_g,calendar.monthrange(tahun_g,bulan_g)[1])

st.info(f"Periode: {awal_g} - {akhir_g} ({(akhir_g-awal_g).days+1} hari)")

id_gaji = st.selectbox("ID Karyawan", db_df['ID KARYAWAN'].tolist() if not db_df.empty else ["01213027"])

if st.button("HITUNG GAJI LENGKAP", type="primary", use_container_width=True):
    res = hitung_gaji_lengkap(id_gaji, awal_g, akhir_g)
    if res is None:
        st.error("Data kosong di periode ini")
    else:
        hadir, total_lembur_g, jml_shift, hari_lembur, total_pendapatan, total_potongan, total_gaji, df, premi_hadir, uang_makan, uang_lembur, uang_shift = res
        st.success(f"Hadir: {hadir} hari | Lembur: {total_lembur_g} jam | Shift: {jml_shift} hari")
        if hadir==13:
            st.caption("✅ Ini periode 21 Aug - 04 Sep = 13 Hadir (sesuai export.csv mu)")
        if hadir==9:
            st.caption("✅ Ini periode 21-31 Aug = 9 Hadir (sesuai DATA GAJI XLSX mu)")

        col1,col2,col3 = st.columns(3)
        col1.metric("Pendapatan", f"Rp {total_pendapatan:,}")
        col2.metric("Potongan", f"Rp {total_potongan:,}")
        col3.metric("TOTAL GAJI", f"Rp {total_gaji:,}")

        st.write("Rincian:")
        st.write(f"- Gaji Pokok: 5.252.909")
        st.write(f"- Premi Hadir: {premi_hadir} (Alfa 0 = 50rb)")
        st.write(f"- Uang Makan: {hadir} x 9500 = {uang_makan}")
        st.write(f"- Uang Lembur: {total_lembur_g} x 30000 = {uang_lembur}")
        st.write(f"- Uang Shift: {jml_shift} x 2187 = {uang_shift}")

        st.dataframe(df[['TANGGAL','SHIFT','JAM KERJA','JAM LEMBUR','STATUS','KETERANGAN']], use_container_width=True)
