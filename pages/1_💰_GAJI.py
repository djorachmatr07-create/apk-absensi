import streamlit as st
from datetime import date, timedelta
import calendar

st.set_page_config(page_title="GAJI V14.1", layout="wide")
st.markdown("<h2>💰 GAJI V14 - AUTO DARI ABSEN</h2>", unsafe_allow_html=True)

# === PILIHAN PERIODE BARU ===
mode = st.radio("Mode Periode", ["Bulan Kalender", "Periode 21-20 (Payroll)", "Custom Tanggal"], horizontal=True)

bulan = st.selectbox("Bulan", list(range(1,13)), index=6)
tahun = st.number_input("Tahun", 2020, 2030, 2026)

if mode == "Bulan Kalender":
    tgl_awal = date(tahun, bulan, 1)
    tgl_akhir = date(tahun, bulan, calendar.monthrange(tahun, bulan)[1])
elif mode == "Periode 21-20 (Payroll)":
    # Misal pilih Bulan 7 = periode 21 Juni - 20 Juli
    if bulan == 1:
        tgl_awal = date(tahun-1, 12, 21)
        tgl_akhir = date(tahun, 1, 20)
    else:
        tgl_awal = date(tahun, bulan-1, 21)
        tgl_akhir = date(tahun, bulan, 20)
else:
    # Custom
    c1, c2 = st.columns(2)
    with c1:
        tgl_awal = st.date_input("Dari Tgl", date(tahun, bulan, 1))
    with c2:
        tgl_akhir = st.date_input("Sampai Tgl", date(tahun, bulan, calendar.monthrange(tahun, bulan)[1]))

st.info(f"📅 Periode: {tgl_awal.strftime('%d %b %Y')} s/d {tgl_akhir.strftime('%d %b %Y')} ({(tgl_akhir-tgl_awal).days+1} hari)")

# Lanjut logic lama mu
id_karyawan = st.selectbox("Pilih Karyawan", ["01213027"]) # ambil dari db mu

if st.button("🔍 HITUNG REAL DARI ABSEN", type="primary", use_container_width=True):
    # disini filter absen_df
    # df_filtered = absen_df[(absen_df['TGL_DT'] >= pd.to_datetime(tgl_awal)) & (absen_df['TGL_DT'] <= pd.to_datetime(tgl_akhir))]
    st.success(f"HITUNG {id_karyawan} PERIODE {tgl_awal} - {tgl_akhir}")
    #... lanjut hitung gaji mu
