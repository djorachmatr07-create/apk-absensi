# RUMUS LENGKAP GAJI - COPY INI DI pages/1_💰_GAJI.py
def hitung_rumus_lengkap(df_rekap, gaji_pokok=5252909):
    # df_rekap = DataFrame REKAP ABSENSI yang udah difilter periode
    
    # --- DASAR ---
    hadir = len(df_rekap[df_rekap['STATUS']=='H']) # 13 Hari di SS mu
    alfa = len(df_rekap[df_rekap['STATUS']=='A'])
    telat = 0 # hitung dari JAM MASUK > jam shift kalau mau
    
    df_rekap['LEMBUR_F'] = pd.to_numeric(df_rekap['JAM LEMBUR'], errors='coerce').fillna(0)
    total_jam_lembur = df_rekap['LEMBUR_F'].sum() # 17.5 Jam di SS mu
    jml_shift = len(df_rekap[(df_rekap['STATUS']=='H') & (df_rekap['SHIFT'].str.contains('S2|S3', na=False))]) # 8 Hari (yang ERROR tadi)
    hari_lembur = len(df_rekap[df_rekap['LEMBUR_F']>0]) # 2 Hari di SS mu

    # --- PENDAPATAN (A) - Kolom C ---
    c3_gaji = gaji_pokok # 5252909
    c4_premi_hadir = 50000 if alfa==0 else 0 # 50000
    c5_uang_makan = hadir * 9500 # 13*9500 = 123500
    c6_uang_transport = hadir * 0 # 0
    c7_uang_lembur = total_jam_lembur * 30000 # 17.5*30000 = 525000 (di SS mu 0 karena rumus error)
    c8_uang_shift = jml_shift * 2187 # 8*2187 = 17496 (di SS mu #ERROR! karena COUNTIF *S2)
    c9_uang_makan_lembur = hari_lembur * 9500 # 2*9500 = 19000
    c10_loyalitas = 3500
    c11_jkk = round(gaji_pokok * 0.0024) # 12606
    c12_jkm = round(gaji_pokok * 0.003) # 15758
    c13_jht_perusahaan = round(gaji_pokok * 0.037) # 194357
    c14_jp_perusahaan = round(gaji_pokok * 0.02) # 105058
    c15_bpjs_perusahaan = round(gaji_pokok * 0.04) # 210116

    total_pendapatan = c3_gaji + c4_premi_hadir + c5_uang_makan + c6_uang_transport + c7_uang_lembur + c8_uang_shift + c9_uang_makan_lembur + c10_loyalitas + c11_jkk + c12_jkm + c13_jht_perusahaan + c14_jp_perusahaan + c15_bpjs_perusahaan
    # total_pendapatan = 6529300 kayak di SS mu (kalau shift & lembur bener)

    # --- POTONGAN (D) - Kolom E ---
    e3_jkk = c11_jkk
    e4_jkm = c12_jkm
    e5_jht_perusahaan = c13_jht_perusahaan
    e6_jp_perusahaan = c14_jp_perusahaan
    e7_bpjs_perusahaan = c15_bpjs_perusahaan
    e8_jht_tk = round(gaji_pokok * 0.02) # 105058
    e9_jp_tk = round(gaji_pokok * 0.01) # 52529
    e10_bpjs_karyawan = round(gaji_pokok * 0.01) # 52529

    total_potongan = e3_jkk + e4_jkm + e5_jht_perusahaan + e6_jp_perusahaan + e7_bpjs_perusahaan + e8_jht_tk + e9_jp_tk + e10_bpjs_karyawan # 748011

    # --- TOTAL GAJI ---
    total_gaji = total_pendapatan - total_potongan # 5781289 kayak di SS mu

    return {
        "B4": f"{telat} Telat", "C4": c4_premi_hadir,
        "B5": f"{hadir} Hari x 9500", "C5": c5_uang_makan,
        "B6": f"{hadir} Hari x 0", "C6": c6_uang_transport,
        "B7": f"{total_jam_lembur} Jam x 30000", "C7": c7_uang_lembur,
        "B8": f"{jml_shift} Hari x 2187", "C8": c8_uang_shift,
        "B9": f"{hari_lembur} Hari x 9500", "C9": c9_uang_makan_lembur,
        "C17": total_pendapatan, "E17": total_potongan, "C19": total_gaji
    }
