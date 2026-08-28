import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from datetime import datetime

st.set_page_config(layout="wide", page_title="REKAP GAJI")
st.markdown("""
<style>
   .stDataFrame { font-size: 12px; }
    section[data-testid="stSidebar"] { width: 250px!important; }
</style>
""", unsafe_allow_html=True)

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

def to_float(x):
    try:
        if pd.isna(x): return 0
        return float(str(x).replace(',','.').replace('Rp','').strip())
    except: return 0

# === SIDEBAR MENU ===
with st.sidebar:
    st.title("📋 MENU UTAMA")
    menu = st.radio("Pilih Menu:", ["📅 ABSEN", "💰 GAJI"], index=0)
    st.divider()
    st.caption(f"Total Karyawan: {len(db_df)}")
    st.caption(f"Total Absen: {len(absen_df)}")

# === MENU ABSEN LENGKAP ===
if menu == "📅 ABSEN":
    st.title("📅 MENU ABSENSI")
    tab1, tab2 = st.tabs(["📊 LIHAT REKAP", "✏️ INPUT ABSEN"])

    with tab1:
        col1, col2, col3 = st.columns(3)
        with col1:
            bulan = st.selectbox("Bulan", range(1,13), index=7, key="b1")
        with col2:
            tahun = st.number_input("Tahun", value=2026, key="t1")
        with col3:
            id_filter = st.selectbox("Karyawan", ["SEMUA"] + db_df['ID KARYAWAN'].tolist(), key="f1")

        df_show = absen_df[(absen_df['TANGGAL'].dt.month==bulan) & (absen_df['TANGGAL'].dt.year==tahun)].copy()
        if id_filter!= "SEMUA":
            df_show = df_show[df_show['ID KARYAWAN']==id_filter]

        # FIX TANGGAL BIAR GAK 00:00:00
        if not df_show.empty and 'TANGGAL' in df_show.columns:
            df_show['TANGGAL_VIEW'] = df_show['TANGGAL'].dt.strftime('%d-%m-%Y')
            # Pindah kolom VIEW ke depan
            cols = ['TANGGAL_VIEW'] + [c for c in df_show.columns if c!= 'TANGGAL_VIEW']
            st.dataframe(df_show[cols], use_container_width=True, height=600)
        else:
            st.warning("Gak ada data bulan ini")
            st.dataframe(df_show, use_container_width=True)

    with tab2:
        st.subheader("Input Absen Baru")
        with st.form("input_absen"):
            col1, col2 = st.columns(2)
            with col1:
                in_id = st.selectbox("ID Karyawan", db_df['ID KARYAWAN'].tolist())
                in_tgl = st.date_input("Tanggal", datetime.now())
                in_shift = st.selectbox("Shift", ["H-S1","H-S2","H-S3","H-LS","T","A","L","LIBUR"])
            with col2:
                in_masuk = st.text_input("Jam Masuk (07:02)", "07:00")
                in_pulang = st.text_input("Jam Pulang (15:05)", "15:00")
                in_jamkerja = st.number_input("Jam Kerja", value=7.0)
                in_lembur = st.number_input("Jam Lembur", value=0.0)

            submit = st.form_submit_button("💾 SIMPAN ABSEN", type="primary", use_container_width=True)
            if submit:
                new_row = [str(in_id), str(in_tgl), in_shift, in_masuk, in_pulang, in_jamkerja, in_lembur, 0, 0]
                ws_absen.append_row(new_row)
                st.success(f"✅ Absen {in_id} tgl {in_tgl} shift {in_shift} berhasil simpan!")
                st.cache_data.clear()

# === MENU GAJI ===
else:
    st.title("💰 GAJI V19 - FIX SABTU LEMBUR")
    if 'df_final' not in st.session_state: st.session_state['df_final'] = None

    bulan = st.selectbox("Bulan Gaji", range(1,13), index=7)
    tahun = st.number_input("Tahun Gaji", value=2026)
    id_pilih = st.selectbox("Pilih Karyawan", db_df['ID KARYAWAN'].tolist())

    if st.button("🔍 HITUNG GAJI REAL", type="primary", use_container_width=True):
        with st.spinner("Ngitung..."):
            absen_bulan = absen_df[(absen_df['TANGGAL'].dt.month==bulan) & (absen_df['TANGGAL'].dt.year==tahun)].copy()
            kar = db_df[db_df['ID KARYAWAN']==id_pilih].iloc[0]
            data_kar = absen_bulan[absen_bulan['ID KARYAWAN']==id_pilih].copy()

            gaji_pokok = to_float(kar.get('GAJI BULAN', 5252909))
            u_makan = to_float(kar.get('UANG MAKAN', 9500))
            u_transport = to_float(kar.get('UANG TRANSPORT', 0))
            u_shift_rate = to_float(kar.get('UANG SHIFT', 2187.5))
            premi_full = to_float(kar.get('PREMI HADIR', 75000))
            loyal = to_float(kar.get('LOYALITAS', 3500))

            hari_kerja=0; hari_telat=0; hari_shift=0; jam_lembur_total=0; l15_total=0; l20_total=0; hari_makan_lembur=0
            for _, row in data_kar.iterrows():
                tgl=row['TANGGAL']
                if pd.isna(tgl): continue
                is_sabtu=tgl.weekday()==5; is_minggu=tgl.weekday()==6
                shift=str(row.get('SHIFT','')).upper()
                jam_kerja=to_float(row.get('JAM KERJA',0))
                jam_lembur=to_float(row.get('JAM LEMBUR',0))
                l15=to_float(row.get('LEMBUR 1.5',0)); l20=to_float(row.get('LEMBUR 2.0',0))
                if (is_sabtu or is_minggu) and ('H-' in shift or shift.startswith('H')):
                    if jam_kerja>0: l20_total+=jam_kerja; jam_lembur_total+=jam_kerja
                    else: l20_total+=7; jam_lembur_total+=7
                    continue
                if 'H-' in shift:
                    hari_kerja+=1
                    if 'S2' in shift or 'S3' in shift: hari_shift+=1
                    jam_lembur_total+=jam_lembur; l15_total+=l15; l20_total+=l20
                    if jam_lembur>=2: hari_makan_lembur+=1
                if 'TL' in shift or shift=='T': hari_telat+=1

            total_makan=hari_kerja*u_makan; total_transport=hari_kerja*u_transport
            total_shift=hari_shift*u_shift_rate; total_makan_lembur=hari_makan_lembur*9500
            rate_per_jam=gaji_pokok/173
            total_lembur=(l15_total*rate_per_jam*1.5)+(l20_total*rate_per_jam*2.0)
            if total_lembur==0 and jam_lembur_total>0: total_lembur=jam_lembur_total*rate_per_jam*2.0
            premi=premi_full if hari_telat==0 else (50000 if hari_telat==1 else max(0,premi_full-hari_telat*25000))
            jkk=gaji_pokok*0.0024; jkm=gaji_pokok*0.0030; jht_prsh=gaji_pokok*0.037; jp_prsh=gaji_pokok*0.02
            bpjs_prsh=gaji_pokok*0.04; jht_tk=gaji_pokok*0.02; jp_tk=gaji_pokok*0.01; bpjs_kar=gaji_pokok*0.01
            total_bpjs_prsh=jkk+jkm+jht_prsh+jp_prsh+bpjs_prsh; total_bpjs_kar=jht_tk+jp_tk+bpjs_kar
            total_potongan=total_bpjs_prsh+total_bpjs_kar
            total_pendapatan=gaji_pokok+premi+total_makan+total_transport+total_lembur+total_shift+total_makan_lembur+loyal+total_bpjs_prsh
            total_gaji=total_pendapatan-total_potongan

            slip=[
                ["PENDAPATAN","","","POTONGAN",""],
                ["Gaji","",int(gaji_pokok),"JKK (0.24%)",int(jkk)],
                ["Premi Hadir",f"{hari_telat} Telat",int(premi),"JKM (0.30%)",int(jkm)],
                ["Uang Makan",f"{hari_kerja} Hari x {int(u_makan)}",int(total_makan),"JHT Perusahaan (3.7%)",int(jht_prsh)],
                ["Uang Transport",f"{hari_kerja} Hari x {int(u_transport)}",int(total_transport),"JP Perusahaan (2%)",int(jp_prsh)],
                ["Uang Lembur",f"{jam_lembur_total} Jam (1.5x={l15_total}, 2.0x={l20_total})",int(total_lembur),"BPJS Kes Perusahaan (4%)",int(bpjs_prsh)],
                ["Uang Shift",f"{hari_shift} Hari",int(total_shift),"JHT TK (2%)",int(jht_tk)],
                ["Uang Makan Lembur",f"{hari_makan_lembur} Hari",int(total_makan_lembur),"JP TK (1%)",int(jp_tk)],
                ["Tunjangan Loyalitas","",int(loyal),"BPJS Kes Karyawan (1%)",int(bpjs_kar)],
                ["JKK","","", "", ""],
                ["TOTAL PENDAPATAN","",int(total_pendapatan),"TOTAL POTONGAN",int(total_potongan)],
                ["TOTAL GAJI","",int(total_gaji),"",""],
            ]
            df=pd.DataFrame(slip, columns=["PENDAPATAN","KET","JUMLAH","POTONGAN","JUMLAH2"])
            st.session_state['df_final']=df
            st.dataframe(df, use_container_width=True)
            st.success(f"Gaji: Rp {int(total_gaji):,} | Kerja {hari_kerja} hari + Lembur Sabtu {l20_total} jam")

    if st.session_state['df_final'] is not None:
        if st.button("💾 SIMPAN KE DATA GAJI", type="primary"):
            df=st.session_state['df_final']
            ws_gaji.clear()
            ws_gaji.update("A1", [df.columns.tolist()] + df.astype(str).values.tolist(), value_input_option="USER_ENTERED")
            st.balloons(); st.success("Berhasil!")
