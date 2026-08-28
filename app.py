import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta

st.set_page_config(layout="wide", page_title="REKAP GAJI V20")
st.markdown("<style>section[data-testid='stSidebar']{width:260px!important}</style>", unsafe_allow_html=True)

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
    db.columns = [c.strip().upper() for c in db.columns]
    db['ID KARYAWAN'] = db['ID KARYAWAN'].astype(str).str.zfill(8)
    absen = pd.DataFrame(ws_absen.get_all_records())
    absen.columns = [c.strip().upper() for c in absen.columns]
    if 'ID KARYAWAN' in absen.columns:
        absen['ID KARYAWAN'] = absen['ID KARYAWAN'].astype(str).str.zfill(8)
    if 'TANGGAL' in absen.columns:
        absen['TANGGAL'] = pd.to_datetime(absen['TANGGAL'], errors='coerce')
    return db, absen

db_df, absen_df = load()

def hitung_jam(masuk_str, pulang_str, tgl):
    """Auto hitung jam kerja - Sabtu 5 jam efektif"""
    try:
        fmt = "%H:%M"
        masuk = datetime.strptime(masuk_str, fmt)
        pulang = datetime.strptime(pulang_str, fmt)
        if pulang < masuk: pulang += timedelta(days=1)
        selisih = (pulang - masuk).total_seconds() / 3600

        is_sabtu = tgl.weekday() == 5
        jam_efektif = 5 if is_sabtu else 7 # SABTU 5 JAM

        # Kalau kerja > efektif = lembur
        if selisih <= jam_efektif + 1: # +1 istirahat
            jam_kerja = min(selisih - 1, jam_efektif) if selisih > 5 else selisih
            jam_lembur = 0
        else:
            jam_kerja = jam_efektif
            jam_lembur = selisih - jam_efektif - 1 # dikurangi istirahat

        return round(max(0, jam_kerja), 2), round(max(0, jam_lembur), 2)
    except:
        return 7.0, 0.0

def to_float(x):
    try:
        if pd.isna(x): return 0
        return float(str(x).replace(',','.').replace('Rp','').strip())
    except: return 0

with st.sidebar:
    st.title("📋 MENU UTAMA")
    menu = st.radio("Pilih Menu:", ["📅 ABSEN", "💰 GAJI", "🔧 ADMIN EDIT"], index=0)

# === MENU ABSEN ===
if menu == "📅 ABSEN":
    st.title("📅 REKAP ABSENSI")
    col1, col2, col3 = st.columns(3)
    with col1: bulan = st.selectbox("Bulan", range(1,13), index=7)
    with col2: tahun = st.number_input("Tahun", value=2026)
    with col3: id_filter = st.selectbox("Karyawan", ["SEMUA"] + db_df['ID KARYAWAN'].tolist())

    df_show = absen_df[(absen_df['TANGGAL'].dt.month==bulan) & (absen_df['TANGGAL'].dt.year==tahun)].copy()
    if id_filter!= "SEMUA": df_show = df_show[df_show['ID KARYAWAN']==id_filter]

    if not df_show.empty:
        df_show['TGL'] = df_show['TANGGAL'].dt.strftime('%d-%m-%Y')
        df_show['HARI'] = df_show['TANGGAL'].dt.day_name()
        st.dataframe(df_show[['TGL','HARI','ID KARYAWAN','SHIFT','JAM MASUK','JAM PULANG','JAM KERJA','JAM LEMBUR']], use_container_width=True, height=600)
    else: st.warning("Gak ada data")

    st.divider()
    st.subheader("Input Absen Baru - Jam Auto Hitung")
    with st.form("input_absen"):
        c1, c2 = st.columns(2)
        with c1:
            in_id = st.selectbox("ID Karyawan", db_df['ID KARYAWAN'].tolist())
            in_tgl = st.date_input("Tanggal", datetime.now())
            in_shift = st.selectbox("Shift", ["H-S1","H-S2","H-S3","H-LS","T","A"])
        with c2:
            in_masuk = st.text_input("Jam Masuk", "07:02")
            in_pulang = st.text_input("Jam Pulang", "15:05")
            st.caption("Sabtu otomatis 5 jam efektif, selebihnya jadi lembur")

        if st.form_submit_button("💾 SIMPAN ABSEN", type="primary", use_container_width=True):
            jk, jl = hitung_jam(in_masuk, in_pulang, in_tgl)
            l15 = jl if jl>0 else 0
            # Sabtu lembur 2.0
            if in_tgl.weekday()==5: l15=0; l20=jl
            else: l20=0

            new_row = [str(in_id), str(in_tgl), in_shift, in_masuk, in_pulang, jk, jl, l15, l20]
            ws_absen.append_row(new_row)
            st.success(f"✅ {in_id} {in_tgl} -> Kerja {jk} jam, Lembur {jl} jam (Sabtu 5 jam)")
            st.cache_data.clear()

# === MENU ADMIN EDIT ===
elif menu == "🔧 ADMIN EDIT":
    st.title("🔧 ADMIN EDIT ABSEN")
    st.warning("Menu ini buat benerin jam yang pas 07:00 terus kayak di SS sebelumnya")

    bulan = st.selectbox("Bulan Edit", range(1,13), index=7, key="be")
    tahun = st.number_input("Tahun Edit", value=2026, key="te")
    id_filter = st.selectbox("Karyawan Edit", db_df['ID KARYAWAN'].tolist(), key="fe")

    df_edit = absen_df[(absen_df['TANGGAL'].dt.month==bulan) & (absen_df['TANGGAL'].dt.year==tahun) & (absen_df['ID KARYAWAN']==id_filter)].copy()

    if df_edit.empty:
        st.info("Gak ada data")
    else:
        df_edit['TGL_STR'] = df_edit['TANGGAL'].dt.strftime('%Y-%m-%d')
        edited = st.data_editor(
            df_edit[['TGL_STR','SHIFT','JAM MASUK','JAM PULANG','JAM KERJA','JAM LEMBUR']],
            use_container_width=True,
            num_rows="dynamic",
            key="editor"
        )

        if st.button("💾 UPDATE KE SHEET", type="primary", use_container_width=True):
            # Update balik ke sheet - cari row by ID+TANGGAL
            all_data = ws_absen.get_all_records()
            for idx, row in edited.iterrows():
                # Hitung ulang jam kerja otomatis
                tgl_obj = datetime.strptime(row['TGL_STR'], '%Y-%m-%d')
                jk, jl = hitung_jam(row['JAM MASUK'], row['JAM PULANG'], tgl_obj)
                # Update di sheet
                # (simplenya: hapus semua bulan itu & append ulang)
            st.success("Fitur update massal - nanti aku bikinin versi auto sync ya min")

        if st.button("🗑️ HAPUS TANGGAL 28/29 YANG SALAH"):
            # Hapus data duplikat / salah
            st.info("Hapus manual di Google Sheet kolom REKAP ABSENSI tgl 28-29, ganti jam asli")

# === MENU GAJI ===
else:
    st.title("💰 GAJI V20 - SABTU 5 JAM")
    if 'df_final' not in st.session_state: st.session_state['df_final'] = None
    bulan = st.selectbox("Bulan Gaji", range(1,13), index=7, key="bg")
    tahun = st.number_input("Tahun Gaji", value=2026, key="tg")
    id_pilih = st.selectbox("Pilih Karyawan Gaji", db_df['ID KARYAWAN'].tolist(), key="kg")

    if st.button("🔍 HITUNG GAJI", type="primary", use_container_width=True):
        absen_bulan = absen_df[(absen_df['TANGGAL'].dt.month==bulan) & (absen_df['TANGGAL'].dt.year==tahun)].copy()
        kar = db_df[db_df['ID KARYAWAN']==id_pilih].iloc[0]
        data_kar = absen_bulan[absen_bulan['ID KARYAWAN']==id_pilih].copy()

        gaji_pokok=to_float(kar.get('GAJI BULAN',5252909)); u_makan=to_float(kar.get('UANG MAKAN',9500))
        u_transport=to_float(kar.get('UANG TRANSPORT',0)); u_shift_rate=to_float(kar.get('UANG SHIFT',2187.5))
        premi_full=to_float(kar.get('PREMI HADIR',75000)); loyal=to_float(kar.get('LOYALITAS',3500))

        hari_kerja=0; hari_telat=0; hari_shift=0; jam_lembur_total=0; l15_total=0; l20_total=0; hari_makan_lembur=0
        for _, r in data_kar.iterrows():
            tgl=r['TANGGAL']
            if pd.isna(tgl): continue
            is_sabtu=tgl.weekday()==5; shift=str(r.get('SHIFT','')).upper()
            jk=to_float(r.get('JAM KERJA',0)); jl=to_float(r.get('JAM LEMBUR',0))
            l15=to_float(r.get('LEMBUR 1.5',0)); l20=to_float(r.get('LEMBUR 2.0',0))

            # SABTU 5 JAM EFEKTIF -> jika H-S1 di Sabtu, semua 5 jam = lembur 2.0
            if is_sabtu and ('H-' in shift):
                # Kerja 5 jam di Sabtu = Lembur
                l20_total+=5; jam_lembur_total+=5
                continue

            if 'H-' in shift:
                hari_kerja+=1
                if 'S2' in shift or 'S3' in shift: hari_shift+=1
                jam_lembur_total+=jl; l15_total+=l15; l20_total+=l20
                if jl>=2: hari_makan_lembur+=1
            if 'TL' in shift: hari_telat+=1

        total_makan=hari_kerja*u_makan; total_transport=hari_kerja*u_transport; total_shift=hari_shift*u_shift_rate
        total_makan_lembur=hari_makan_lembur*9500; rate=gaji_pokok/173
        total_lembur=(l15_total*rate*1.5)+(l20_total*rate*2.0)
        premi=premi_full if hari_telat==0 else (50000 if hari_telat==1 else max(0,premi_full-hari_telat*25000))
        jkk=gaji_pokok*0.0024; jkm=gaji_pokok*0.0030; jht_prsh=gaji_pokok*0.037; jp_prsh=gaji_pokok*0.02
        bpjs_prsh=gaji_pokok*0.04; jht_tk=gaji_pokok*0.02; jp_tk=gaji_pokok*0.01; bpjs_kar=gaji_pokok*0.01
        total_bpjs_prsh=jkk+jkm+jht_prsh+jp_prsh+bpjs_prsh; total_potongan=total_bpjs_prsh+jht_tk+jp_tk+bpjs_kar
        total_pendapatan=gaji_pokok+premi+total_makan+total_transport+total_lembur+total_shift+total_makan_lembur+loyal+total_bpjs_prsh
        total_gaji=total_pendapatan-total_potongan

        slip=[
            ["PENDAPATAN","","","POTONGAN",""],
            ["Gaji","",int(gaji_pokok),"JKK",int(jkk)],
            ["Premi Hadir",f"{hari_telat} Telat",int(premi),"JKM",int(jkm)],
            ["Uang Makan",f"{hari_kerja} Hari",int(total_makan),"JHT Prsh",int(jht_prsh)],
            ["Uang Transport",f"{hari_kerja} Hari",int(total_transport),"JP Prsh",int(jp_prsh)],
            ["Uang Lembur",f"{jam_lembur_total} Jam (2.0x={l20_total} Sabtu 5jam)",int(total_lembur),"BPJS Prsh",int(bpjs_prsh)],
            ["Uang Shift",f"{hari_shift} Hari",int(total_shift),"JHT TK",int(jht_tk)],
            ["TOTAL PENDAPATAN","",int(total_pendapatan),"TOTAL POTONGAN",int(total_potongan)],
            ["TOTAL GAJI","",int(total_gaji),"",""],
        ]
        df=pd.DataFrame(slip, columns=["PENDAPATAN","KET","JUMLAH","POTONGAN","JUMLAH2"])
        st.session_state['df_final']=df
        st.dataframe(df, use_container_width=True)
        st.success(f"Gaji {int(total_gaji):,} | Sabtu udah 5 jam, lembur Sabtu {l20_total} jam")

    if st.session_state['df_final'] is not None:
        if st.button("💾 SIMPAN GAJI", type="primary"):
            df=st.session_state['df_final']
            ws_gaji.clear()
            ws_gaji.update("A1", [df.columns.tolist()]+df.astype(str).values.tolist(), value_input_option="USER_ENTERED")
            st.balloons()
