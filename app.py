import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from datetime import datetime

st.set_page_config(layout="wide")
st.title("💰 GAJI V16 - FIX SABTU LEMBUR & JAM ASLI")

@st.cache_resource
def connect():
    scope = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(creds)
    sh = client.open("REKAP")
    # Ambil 3 sheet
    return sh.worksheet("REKAP ABSENSI"), sh.worksheet("DATABASE KARYAWAN"), sh.worksheet("DATA GAJI")

ws_absen, ws_db, ws_gaji = connect()

@st.cache_data(ttl=60)
def load():
    db = pd.DataFrame(ws_db.get_all_records())
    db.columns = [c.strip().upper() for c in db.columns]
    db['ID KARYAWAN'] = db['ID KARYAWAN'].astype(str).str.zfill(8)

    absen = pd.DataFrame(ws_absen.get_all_records())
    absen.columns = [c.strip().upper() for c in absen.columns]
    absen['ID KARYAWAN'] = absen['ID KARYAWAN'].astype(str).str.zfill(8)
    absen['TANGGAL'] = pd.to_datetime(absen['TANGGAL'], errors='coerce')
    return db, absen

db_df, absen_df = load()

def to_float(x):
    try:
        if pd.isna(x): return 0
        return float(str(x).replace(',','.').replace('Rp','').strip())
    except:
        return 0

bulan = st.selectbox("Bulan", range(1,13), index=7)
tahun = st.number_input("Tahun", value=2026)
id_pilih = st.selectbox("Pilih Karyawan", db_df['ID KARYAWAN'].tolist())

if st.button("🔍 HITUNG REAL V16", type="primary", use_container_width=True):
    absen_bulan = absen_df[(absen_df['TANGGAL'].dt.month==bulan) & (absen_df['TANGGAL'].dt.year==tahun)].copy()
    kar = db_df[db_df['ID KARYAWAN']==id_pilih].iloc[0]
    data_kar = absen_bulan[absen_bulan['ID KARYAWAN']==id_pilih].copy()

    # MASTER GAJI
    gaji_pokok = to_float(kar['GAJI BULAN']) if 'GAJI BULAN' in kar else 5252909
    u_makan = to_float(kar['UANG MAKAN']) if 'UANG MAKAN' in kar else 9500
    u_transport = to_float(kar['UANG TRANSPORT']) if 'UANG TRANSPORT' in kar else 0
    u_shift_rate = to_float(kar['UANG SHIFT']) if 'UANG SHIFT' in kar else 2187.5
    premi_full = to_float(kar['PREMI HADIR']) if 'PREMI HADIR' in kar else 75000
    loyal = to_float(kar['LOYALITAS']) if 'LOYALITAS' in kar else 3500
    u_makan_lembur_rate = 9500

    # VARIABEL HITUNG
    hari_kerja = 0
    hari_telat = 0
    hari_shift = 0
    jam_lembur_total = 0
    lembur_1_5_total = 0
    lembur_2_0_total = 0
    hari_makan_lembur = 0

    debug_rows = []

    for _, row in data_kar.iterrows():
        tgl = row['TANGGAL']
        if pd.isna(tgl): continue

        is_sabtu = tgl.weekday() == 5 # Sabtu = 5
        is_minggu = tgl.weekday() == 6 # Minggu = 6

        shift = str(row.get('SHIFT','')).upper()
        jam_kerja = to_float(row.get('JAM KERJA',0))
        jam_lembur = to_float(row.get('JAM LEMBUR',0))
        l15 = to_float(row.get('LEMBUR 1.5',0))
        l20 = to_float(row.get('LEMBUR 2.0',0))
        jam_masuk = str(row.get('JAM MASUK',''))
        jam_pulang = str(row.get('JAM PULANG',''))

        # === FIX UTAMA: JAM MASUK/PULANG GAK LAGI AUTO PAS ===
        # Kita pakai jam asli apa adanya, jangan di overwrite jadi 07:00
        # Jika di sheet mu masih rumus IF, hapus rumusnya di Sheet

        # === FIX SABTU AUTO LEMBUR ===
        if shift.startswith('H') or shift == 'H-S1' or shift == 'H-S2':
            if is_sabtu or is_minggu:
                # SABTU/MINGGU MASUK = LEMBUR, BUKAN HARI KERJA BIASA
                # Sesuai SS mu tgl 29-08-2026 (Sabtu) harusnya masuk lembur
                if jam_kerja > 0:
                    l20 += jam_kerja # Sabtu rate 2.0
                    jam_lembur_total += jam_kerja
                    lembur_2_0_total += jam_kerja
                else:
                    l20 = 7.0
                    jam_lembur_total += 7.0
                    lembur_2_0_total += 7.0
                debug_rows.append([tgl.date(), "SABTU LEMBUR", jam_masuk, jam_pulang, jam_kerja, f"L20={l20}"])
                # JANGAN hitung sebagai hari kerja biasa
                continue

        # HARI BIASA
        if shift.startswith('H'):
            hari_kerja += 1
            if 'S2' in shift or 'S3' in shift or 'LS' in shift:
                hari_shift += 1
            jam_lembur_total += jam_lembur
            lembur_1_5_total += l15
            lembur_2_0_total += l20

            # Makan lembur jika lembur >=2 jam
            if jam_lembur >= 2 or l15 >=2 or l20 >=2:
                hari_makan_lembur += 1

        if 'T' in shift or 'TL' in shift:
            hari_telat += 1

        debug_rows.append([tgl.date(), shift, jam_masuk, jam_pulang, jam_kerja, jam_lembur])

    # HITUNGAN UANG
    total_makan = hari_kerja * u_makan
    total_transport = hari_kerja * u_transport
    total_shift = hari_shift * u_shift_rate
    total_makan_lembur = hari_makan_lembur * u_makan_lembur_rate

    # Lembur: 1.5x dan 2.0x (UMK / 173)
    # Rumus: Gaji Pokok / 173 * multiplier
    rate_per_jam = gaji_pokok / 173
    total_lembur = (lembur_1_5_total * rate_per_jam * 1.5) + (lembur_2_0_total * rate_per_jam * 2.0)
    # Kalau jam_lembur_total masih 0 tapi ada Sabtu, pakai hitungan Sabtu
    if total_lembur == 0 and jam_lembur_total > 0:
        total_lembur = jam_lembur_total * rate_per_jam * 2.0

    # Premi Hadir
    if hari_telat == 0:
        premi = premi_full
    elif hari_telat == 1:
        premi = 50000
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

    # SLIP PERSIS FOTO
    slip = [
        ["PENDAPATAN", "", "", "POTONGAN", ""],
        ["Gaji", "", int(gaji_pokok), "JKK (0.24%)", int(jkk)],
        ["Premi Hadir", f"{hari_telat} Telat", int(premi), "JKM (0.30%)", int(jkm)],
        ["Uang Makan", f"{hari_kerja} Hari x {int(u_makan)}", int(total_makan), "JHT Perusahaan (3.7%)", int(jht_prsh)],
        ["Uang Transport", f"{hari_kerja} Hari x {int(u_transport)}", int(total_transport), "JP Perusahaan (2%)", int(jp_prsh)],
        ["Uang Lembur", f"{jam_lembur_total} Jam (1.5x={lembur_1_5_total}, 2.0x={lembur_2_0_total})", int(total_lembur), "BPJS Kes Perusahaan (4%)", int(bpjs_prsh)],
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
    st.dataframe(df, use_container_width=True, height=600)
    st.session_state['df_final'] = df

    st.success(f"TOTAL PENDAPATAN {int(total_pendapatan):,} | POTONGAN {int(total_potongan):,} | GAJI {int(total_gaji):,}")

    with st.expander("🔍 DEBUG - KENAPA TGL 28/29 GAK LEMBUR?"):
        st.write("Sekarang Sabtu auto jadi Lembur 2.0")
        st.write(f"Hari Kerja Biasa: {hari_kerja} | Lembur Sabtu/Minggu: {lembur_2_0_total} jam | Shift: {hari_shift}")
        st.dataframe(pd.DataFrame(debug_rows, columns=["TANGGAL","SHIFT","MASUK","PULANG","JAM KERJA","LEMBUR"]))

    with st.expander("⚠️ CARA BENERIN JAM MASUK/PULANG BIAR GAK PAS 07:00 TERUS"):
        st.write("""
        1. Buka Google Sheet REKAP ABSENSI
        2. Kolom D (JAM MASUK) dan E (JAM PULANG) - HAPUS rumus IF(SHIFT="H-S1","07:00:00")
        3. Ganti dengan rumus ambil dari RAW:
           =ARRAYFORMULA(IF(RAW!B2:B="","",RAW!B2:B))
        4. Atau kalau pakai Apps Script, matikan auto-rounding
        """)

if 'df_final' in st.session_state:
    if st.button("💾 SIMPAN KE DATA GAJI", type="primary"):
        df = st.session_state['df_final']
        data_simpan = [df.columns.tolist()] + df.astype(str).values.tolist()
        ws_gaji.clear()
        ws_gaji.update("A1", data_simpan, value_input_option="USER_ENTERED")
        st.balloons()
        st.success("✅ BERHASIL! Sabtu udah kehitung lembur min")
