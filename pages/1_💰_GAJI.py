import streamlit as st, gspread, pandas as pd, calendar, io
from datetime import date
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="GAJI V16 XLSX", layout="wide", page_icon="💰")

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

def generate_xlsx(id_kar, tgl_awal, tgl_akhir):
    df = absen_df[(absen_df['ID KARYAWAN']==id_kar) & (absen_df['TGL_DT']>=pd.to_datetime(tgl_awal)) & (absen_df['TGL_DT']<=pd.to_datetime(tgl_akhir))].copy()
    if df.empty: return None
    hadir = len(df[df['STATUS']=='H'])
    alfa = len(df[df['STATUS']=='A'])
    df['JAM_LEMBUR_F'] = pd.to_numeric(df['JAM LEMBUR'], errors='coerce').fillna(0)
    total_lembur = df['JAM_LEMBUR_F'].sum()
    jml_shift = len(df[(df['STATUS']=='H') & (df['SHIFT'].str.contains('S2|S3', na=False))])
    hari_lembur = len(df[df['JAM_LEMBUR_F']>0])

    gaji_pokok = 5252909
    premi_hadir = 50000 if alfa==0 else 0
    uang_makan = hadir * 9500
    uang_lembur = total_lembur * 30000
    uang_shift = jml_shift * 2187
    uang_makan_lembur = hari_lembur * 9500
    total_pendapatan = gaji_pokok + premi_hadir + uang_makan + uang_lembur + uang_shift + uang_makan_lembur + 3500 + 12606+15758+194357+105058+210116
    total_potongan = 12606+15758+194357+105058+210116+105058+52529+52529
    total_gaji = total_pendapatan - total_potongan

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # Sheet DATA GAJI format sama kayak SS mu
        gaji_data = [
            ["PENDAPATAN (A)", "KET (B)", "JUMLAH (C)", "POTONGAN (D)", "JUMLAH (E)"],
            ["PENDAPATAN", "", "", "POTONGAN", ""],
            ["Gaji", "", gaji_pokok, "JKK (0.24%)", 12606],
            ["Premi Hadir", f"{0} Telat", premi_hadir, "JKM (0.30%)", 15758],
            ["Uang Makan", f"{hadir} Hari x 9500", uang_makan, "JHT Perusahaan (3.7%)", 194357],
            ["Uang Transport", f"{hadir} Hari x 0", 0, "JP Perusahaan (2%)", 105058],
            ["Uang Lembur", f"{total_lembur} Jam x 30000", uang_lembur, "BPJS Kes Perusahaan (4%)", 210116],
            ["Uang Shift", f"{jml_shift} Hari x 2187", uang_shift, "JHT TK (2%)", 105058],
            ["Uang Makan Lembur", f"{hari_lembur} Hari x 9500", uang_makan_lembur, "JP TK (1%)", 52529],
            ["Tunjangan Loyalitas", "", 3500, "BPJS Kes Karyawan (1%)", 52529],
            ["JKK (0.24%)", "", 12606, "", ""],
            ["JKM (0.30%)", "", 15758, "", ""],
            ["JHT Perusahaan (3.7%)", "", 194357, "", ""],
            ["JP Perusahaan (2%)", "", 105058, "", ""],
            ["BPJS Kes Perusahaan (4%)", "", 210116, "", ""],
            ["", "", "", "", ""],
            ["TOTAL PENDAPATAN", "", total_pendapatan, "TOTAL POTONGAN", total_potongan],
            ["", "", "", "", ""],
            ["TOTAL GAJI", "", total_gaji, "", ""],
        ]
        pd.DataFrame(gaji_data).to_excel(writer, sheet_name="DATA GAJI", index=False, header=False)
        df.to_excel(writer, sheet_name="REKAP ABSENSI PERIODE", index=False)
    output.seek(0)
    return output, total_gaji, hadir, total_lembur, jml_shift

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
        awal_g=date(tahun_g-1,12,21) if bulan_g==1 else date(tahun_g,bulan_g-1,21)
        akhir_g=date(tahun_g,1,20) if bulan_g==1 else date(tahun_g,bulan_g,20)
    else:
        awal_g=date(tahun_g,bulan_g,1)
        akhir_g=date(tahun_g,bulan_g,calendar.monthrange(tahun_g,bulan_g)[1])

st.info(f"Periode: {awal_g} - {akhir_g}")
id_gaji = st.selectbox("ID Karyawan", db_df['ID KARYAWAN'].tolist() if not db_df.empty else ["01213027"])

if st.button("HITUNG & GENERATE XLSX", type="primary", use_container_width=True):
    res = generate_xlsx(id_gaji, awal_g, akhir_g)
    if res is None:
        st.error("Data kosong")
    else:
        bio, total_gaji, hadir, total_lembur, jml_shift = res
        st.success(f"Hadir {hadir} | Lembur {total_lembur} | Shift {jml_shift} | TOTAL Rp {total_gaji:,}")
        st.download_button("📥 DOWNLOAD XLSX (Format REKAP)", data=bio, file_name=f"GAJI_{id_gaji}_{awal_g}_{akhir_g}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
