with menu[1]:
    if "login" not in st.session_state: st.session_state.login = False
    if not st.session_state.login:
        pw = st.text_input("Password Admin", type="password", key="pw_edit")
        if st.button("LOGIN", key="btn_login"):
            if pw == PASSWORD_ADMIN: st.session_state.login = True; st.rerun()
            else: st.error("Password Salah")
    else:
        if st.button("LOGOUT", key="btn_logout"): st.session_state.login = False; st.rerun()
        id_edit = st.text_input("ID yg mau diedit", key="id_edit").strip().zfill(8)
        if id_edit in db_df['ID KARYAWAN'].values:
            data_kar = absen_df[absen_df['ID KARYAWAN']==id_edit]
            if not data_kar.empty:
                opsi_tgl = data_kar.dropna(subset=['JAM MASUK DT']).sort_values('JAM MASUK DT')['JAM MASUK'].tolist()
                pilih = st.selectbox("Pilih Tanggal Data", opsi_tgl, key="pilih_tgl_edit")
                row = data_kar[data_kar['JAM MASUK']==pilih].iloc[0]
                
                col1, col2 = st.columns(2)
                with col1:
                    tgl_edit = st.date_input("Tanggal", pd.to_datetime(row['JAM MASUK']).date(), key="tgl_edit")
                    jam_masuk_edit = st.time_input("Jam Masuk", pd.to_datetime(row['JAM MASUK']).time() if row['JAM MASUK'] else datetime.now().time(), key="jam_masuk_edit")
                with col2:
                    jam_pulang_edit = st.time_input("Jam Pulang", pd.to_datetime(row['JAM PULANG']).time() if row['JAM PULANG'] else datetime.now().time(), key="jam_pulang_edit")
                
                DAFTAR_STATUS_EDIT = {"H": "H - HADIR", "GH": "GH - GANTI HARI", "GHS": "GHS - GANTI HARI SABTU", "TL": "TL - TUKAR LIBUR", "A": "A - ALFA", "I": "I - IZIN", "S": "S - SAKIT", "C": "C - CUTI", "L": "L - LIBUR"}
                kode_pilih = st.selectbox("Ubah Status Menjadi", options=list(DAFTAR_STATUS_EDIT.keys()), format_func=lambda x: DAFTAR_STATUS_EDIT[x], key="status_edit")
                
                if st.button("SIMPAN EDIT", use_container_width=True, type="primary", key="btn_simpan_edit"):
                    with st.spinner("Menyimpan data..."):
                        time.sleep(0.3)
                        masuk_dt = datetime.combine(tgl_edit, jam_masuk_edit)
                        pulang_dt = datetime.combine(tgl_edit, jam_pulang_edit)
                        upsert_absen(id_edit, masuk_dt, pulang_dt, row['NAMA KARYAWAN'], kode_pilih, sudah_pulang=True)
                    st.success(f"✅ Edit berhasil. Status: {DAFTAR_STATUS_EDIT[kode_pilih]}") # UDAH DITUTUP
                    st.rerun()
