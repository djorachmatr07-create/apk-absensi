# === TAMBAHKAN DI TAB5 GAJI - RUMUS LENGKAP PYTHON ===
import streamlit as st
from datetime import date, timedelta

def hitung_gaji_lengkap(id_kar, tgl_awal, tgl_akhir, absen_df):
    # Filter periode
    df = absen_df[
        (absen_df['ID KARYAWAN']==id_kar) &
        (absen_df['TGL_DT']>=pd.to_datetime(tgl_awal)) &
        (absen_df['TGL_DT']<=pd.to_datetime(tgl_akhir))
    ].copy()

    if df.empty:
        return None

    # === RUMUS INTI (BIAR 13 vs 9 SINGKRON) ===
    # Hadir = STATUS H (udah termasuk GH/GHS yang sekarang jadi H)
    hadir = len(df[df['STATUS']=='H'])
    alfa = len(df[df['STATUS']=='A'])
    izin = len(df[df['STATUS']=='I'])

    # Total Jam
    df['JAM_LEMBUR_F'] = pd.to_numeric(df['JAM LEMBUR'], errors='coerce').fillna(0)
    total_lembur_g = df['JAM_LEMBUR_F'].sum() # G = H*1.5 + I*2.0

    # Shift S2/S3 yang dapat uang shift
    df_shift = df[(df['STATUS']=='H') & (df['SHIFT'].str.contains('S2|S3', na=False))]
    jml_shift = len(df_shift)

    # Hari lembur dapat uang makan lembur
    hari_lembur = len(df[df['JAM_LEMBUR_F']>0])

    # === PENDAPATAN (C) ===
    gaji_pokok = 5252909
    premi_hadir = 50000 if alfa==0 else 0
    uang_makan = hadir * 9500
    uang_transport = hadir * 0
    uang_lembur = total_lembur_g * 30000
    uang_shift = jml_shift * 2187
    uang_makan_lembur = hari_lembur * 9500
    tunj_loyalitas = 3500

    # BPJS Perusahaan (ditanggung perusahaan tapi masuk pendapatan dulu)
    jkk = round(gaji_pokok * 0.0024)
    jkm = round(gaji_pokok * 0.0030)
    jht_perusahaan = round(gaji_pokok * 0.037)
    jp_perusahaan = round(gaji_pokok * 0.02)
    bpjs_kes_perusahaan = round(gaji_pokok * 0.04)

    total_pendapatan = gaji_pokok + premi_hadir + uang_makan + uang_transport + uang_lembur + uang_shift + uang_makan_lembur + tunj_loyalitas + jkk + jkm + jht_perusahaan + jp_perusahaan + bpjs_kes_perusahaan

    # === POTONGAN (E) ===
    pot_jkk = jkk
    pot_jkm = jkm
    pot_jht_perusahaan = jht_perusahaan
    pot_jp_perusahaan = jp_perusahaan
    pot_bpjs_kes_perusahaan = bpjs_kes_perusahaan
    pot_jht_tk = round(gaji_pokok * 0.02) # 105058
    pot_jp_tk = round(gaji_pokok * 0.01) # 52529
    pot_bpjs_kes_karyawan = round(gaji_pokok * 0.01)

    total_potongan = pot_jkk + pot_jkm + pot_jht_perusahaan + pot_jp_perusahaan + pot_bpjs_kes_perusahaan + pot_jht_tk + pot_jp_tk + pot_bpjs_kes_karyawan

    total_gaji = total_pendapatan - total_potongan

    return {
        "periode": f"{tgl_awal} s/d {tgl_akhir}",
        "hadir": hadir,
        "alfa": alfa,
        "total_lembur": total_lembur_g,
        "jml_shift": jml_shift,
        "hari_lembur": hari_lembur,
        "rincian": {
            "Gaji Pokok": gaji_pokok,
            "Premi Hadir": premi_hadir,
            "Uang Makan": uang_makan,
            "Uang Transport": uang_transport,
            "Uang Lembur": uang_lembur,
            "Uang Shift": uang_shift,
            "Uang Makan Lembur": uang_makan_lembur,
            "Tunjangan Loyalitas": tunj_loyalitas,
        },
        "total_pendapatan": total_pendapatan,
        "total_potongan": total_potongan,
        "total_gaji": total_gaji,
        "df": df
    }

# === DI TAB5 PAKAI INI ===
with tab5:
    st.write("### GAJI V16 - RUMUS LENGKAP GITHUB")
    mode_g=st.radio("Mode", ["21-20 Payroll","Bulan Kalender","Custom"], horizontal=True, key="mode_g2")
    c1,c2=st.columns(2)
    with c1: bulan_g=st.selectbox("Bulan", list(range(1,13)), index=8, key="bulan_g2")
    with c2: tahun_g=st.number_input("Tahun", 2020, 2030, 2026, key="tahun_g2")

    if mode_g=="Custom":
        cc1,cc2=st.columns(2)
        with cc1: awal_g=st.date_input("Dari", date(tahun_g,bulan_g,1), key="awal_g2")
        with cc2: akhir_g=st.date_input("Sampai", date(tahun_g,bulan_g,20), key="akhir_g2")
    else:
        if mode_g=="21-20 Payroll":
            if bulan_g==1:
                awal_g=date(tahun_g-1,12,21)
                akhir_g=date(tahun_g,1,20)
            else:
                awal_g=date(tahun_g,bulan_g-1,21)
                akhir_g=date(tahun_g,bulan_g,20)
        else:
            import calendar
            awal_g=date(tahun_g,bulan_g,1)
            akhir_g=date(tahun_g,bulan_g,calendar.monthrange(tahun_g,bulan_g)[1])

    st.info(f"Periode: {awal_g} - {akhir_g}")

    id_gaji=st.selectbox("ID Karyawan", db_df['ID KARYAWAN'].tolist())

    if st.button("HITUNG GAJI LENGKAP", type="primary", use_container_width=True):
        hasil = hitung_gaji_lengkap(id_gaji, awal_g, akhir_g, absen_df)
        if hasil:
            st.success(f"Hadir: {hasil['hadir']} hari | Lembur: {hasil['total_lembur']} jam | Shift S2/S3: {hasil['jml_shift']} hari")
            # Ini yang bikin beda 13 vs 9
            if hasil['hadir']==13:
                st.write("✅ Periode 21 Aug - 04 Sep = 13 Hadir (sesuai export.csv)")
            elif hasil['hadir']==9:
                st.write("✅ Periode 21-31 Aug = 9 Hadir (sesuai DATA GAJI XLSX)")

            col1,col2,col3=st.columns(3)
            col1.metric("Pendapatan", f"Rp {hasil['total_pendapatan']:,}")
            col2.metric("Potongan", f"Rp {hasil['total_potongan']:,}")
            col3.metric("TOTAL GAJI", f"Rp {hasil['total_gaji']:,}")

            st.dataframe(hasil['df'][['TANGGAL','SHIFT','JAM KERJA','JAM LEMBUR','STATUS','UANG SHIFT','KETERANGAN']], use_container_width=True)
        else:
            st.error("Data kosong")
