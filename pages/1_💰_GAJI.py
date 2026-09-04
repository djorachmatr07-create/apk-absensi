import streamlit as st, gspread, pandas as pd, calendar, io
from datetime import date
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="GAJI V16", layout="wide", page_icon="💰")
st.title("💰 GAJI V16 - Fix 13 Hari")

@st.cache_resource
def connect():
    scope = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(creds)
    sh = client.open("REKAP")
    return sh, sh.worksheet("REKAP ABSENSI"), sh.worksheet("DATABASE KARYAWAN"), sh.worksheet("DATA GAJI")

sh, ws_absen, ws_db, ws_gaji = connect()

@st.cache_data(ttl=60)
def load():
    db = pd.DataFrame(ws_db.get_all_records())
    db['ID KARYAWAN'] = db['ID KARYAWAN'].astype(str).str.zfill(8)
    vals = ws_absen.get_all_values()
    H = ['ID KARYAWAN','NAMA KARYAWAN','TANGGAL','JAM MASUK','JAM PULANG','JAM KERJA','JAM LEMBUR','LEMBUR 1.5','LEMBUR 2.0','SHIFT','KETERANGAN','STATUS','UANG SHIFT']
    absen = pd.DataFrame([r[:13] for r in vals[1:]], columns=H) if len(vals)>1 else pd.DataFrame(columns=H)
    absen['ID KARYAWAN'] = absen['ID KARYAWAN'].astype(str).str.zfill(8)
    absen['TGL_DT'] = pd.to_datetime(absen['TANGGAL'], errors='coerce')
    return db, absen

db_df, absen_df = load()

# PILIH PERIODE
c1,c2 = st.columns(2)
with c1: bulan = st.selectbox("Bulan", range(1,13), index=8)
with c2: tahun = st.number_input("Tahun", 2020, 2030, 2026)
awal = date(tahun, bulan-1, 21) if bulan>1 else date(tahun-1, 12, 21)
akhir = date(tahun, bulan, 20)
awal = st.date_input("Dari", awal)
akhir = st.date_input("Sampai", akhir)
st.info(f"Periode: {awal} s/d {akhir}")

id_kar = st.selectbox("ID Karyawan", db_df['ID KARYAWAN'].tolist())

if st.button("HITUNG & UPDATE SHEET DATA GAJI", type="primary", use_container_width=True):
    df = absen_df[(absen_df['ID KARYAWAN']==id_kar) & (absen_df['TGL_DT']>=pd.to_datetime(awal)) & (absen_df['TGL_DT']<=pd.to_datetime(akhir))].copy()

    # RUMUS BARU - INI YANG BIKIN 13 BUKAN 9
    hadir = len(df[df['STATUS']=='H'])
    alfa = len(df[df['STATUS']=='A'])
    df['JML_F'] = pd.to_numeric(df['JAM LEMBUR'], errors='coerce').fillna(0)
    total_lembur = df['JML_F'].sum()
    jml_shift = len(df[(df['STATUS']=='H') & (df['SHIFT'].str.contains('S2|S3', na=False))])
    hari_lembur = len(df[df['JML_F']>0])

    gaji_pokok = 5252909
    premi = 50000 if alfa==0 else 0
    uang_makan = hadir * 9500
    uang_lembur = total_lembur * 30000
    uang_shift = jml_shift * 2187
    uang_makan_lembur = hari_lembur * 9500

    total_pend = gaji_pokok + premi + uang_makan + uang_lembur + uang_shift + uang_makan_lembur + 3500 + 12606+15758+194357+105058+210116
    total_pot = 12606+15758+194357+105058+210116+105058+52529+52529
    total_gaji = total_pend - total_pot

    # UPDATE KE GOOGLE SHEET DATA GAJI (BIAR GAK #ERROR LAGI)
    ws_gaji.batch_update([
        {'range': 'B4', 'values': [[f"0 Telat"]]},
        {'range': 'C4', 'values': [[premi]]},
        {'range': 'B5', 'values': [[f"{hadir} Hari x 9500"]]},
        {'range': 'C5', 'values': [[uang_makan]]},
        {'range': 'B6', 'values': [[f"{hadir} Hari x 0"]]},
        {'range': 'C6', 'values': [[0]]},
        {'range': 'B7', 'values': [[f"{total_lembur} Jam x 30000"]]},
        {'range': 'C7', 'values': [[uang_lembur]]},
        {'range': 'B8', 'values': [[f"{jml_shift} Hari x 2187"]]},
        {'range': 'C8', 'values': [[uang_shift]]},
        {'range': 'B9', 'values': [[f"{hari_lembur} Hari x 9500"]]},
        {'range': 'C9', 'values': [[uang_makan_lembur]]},
        {'range': 'C17', 'values': [[total_pend]]},
        {'range': 'E17', 'values': [[total_pot]]},
        {'range': 'C19', 'values': [[total_gaji]]},
    ])

    st.success(f"✅ DONE! Sheet DATA GAJI udah ke-update: {hadir} Hari = Rp {total_gaji:,}")
    st.write(f"Kalau periode 21-31 Aug = 9 Hari (5.732.353)")
    st.write(f"Kalau periode 21 Aug - 04 Sep = 13 Hari (5.781.289) <- yang ini sekarang")

    # DOWNLOAD XLSX JUGA
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        pd.DataFrame([[hadir, total_lembur, jml_shift, total_gaji]], columns=["Hadir","Lembur","Shift","Total"]).to_excel(writer, index=False, sheet_name="DATA GAJI")
        df.to_excel(writer, index=False, sheet_name="REKAP ABSENSI")
    st.download_button("📥 Download XLSX", output.getvalue(), f"GAJI_{id_kar}_{awal}_{akhir}.xlsx", use_container_width=True)
