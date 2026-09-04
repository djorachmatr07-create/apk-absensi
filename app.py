import streamlit as st, gspread, pandas as pd, requests, math, calendar
from datetime import datetime, timedelta, date
from google.oauth2.service_account import Credentials
from icalendar import Calendar

st.set_page_config(page_title="NEXA + GAJI", layout="wide", page_icon="🛰️")
st.title("🛰️ NEXA V16 + GAJI 5.7JT")

ICS_URL = "https://calendar.google.com/calendar/ical/id.indonesian%23holiday%40group.v.calendar.google.com/public/basic.ics"

@st.cache_resource
def connect():
    scope = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(creds)
    sh = client.open("REKAP")
    return sh.worksheet("REKAP ABSENSI"), sh.worksheet("DATABASE KARYAWAN"), sh.worksheet("DATA GAJI")
ws_absen, ws_db, ws_gaji = connect()

@st.cache_data(ttl=86400)
def get_libur():
    try:
        r=requests.get(ICS_URL, timeout=10)
        cal=Calendar.from_ical(r.text)
        return {c.get('dtstart').dt.strftime('%Y-%m-%d'): str(c.get('summary')) for c in cal.walk() if c.name=="VEVENT" and hasattr(c.get('dtstart').dt,'strftime')}
    except: return {}
LIBUR=get_libur()

HEADER=['ID KARYAWAN','NAMA KARYAWAN','TANGGAL','JAM MASUK','JAM PULANG','JAM KERJA','JAM LEMBUR','LEMBUR 1.5','LEMBUR 2.0','SHIFT','KETERANGAN','STATUS','UANG SHIFT']

def hitung_lembur(jam_float, is_sabtu=False, is_minggu=False, is_merah=False, status="H"):
    jam_float=math.floor(float(jam_float or 0)+0.5)
    if jam_float<=0: return "0.00","0.00","0.00","0.00"
    if status=="GH": return "7.00","0.00","0.00","0.00"
    if status=="GHS": return "5.00","0.00","0.00","0.00"
    if is_sabtu:
        if jam_float<=5: return "5.00","0.00","0.00","0.00"
        sisa=jam_float-5; l15=1 if sisa>=1 else sisa; l20=sisa-1 if sisa>1 else 0
        return "5.00",f"{l15*1.5+l20*2:.2f}",f"{l15:.2f}",f"{l20:.2f}"
    if is_minggu or is_merah: return "0.00",f"{jam_float*2:.2f}","0.00",f"{jam_float:.2f}"
    if jam_float<=7: return f"{jam_float:.2f}","0.00","0.00","0.00"
    sisa=jam_float-7; l15=1 if sisa>=1 else sisa; l20=sisa-1 if sisa>1 else 0
    return "7.00",f"{l15*1.5+l20*2:.2f}",f"{l15:.2f}",f"{l20:.2f}"

@st.cache_data(ttl=60)
def load():
    db=pd.DataFrame(ws_db.get_all_records()); db['ID KARYAWAN']=db['ID KARYAWAN'].astype(str).str.zfill(8)
    col_uang=[c for c in db.columns if 'UANG' in c.upper() and 'SHIFT' in c.upper()]
    col_uang=col_uang[0] if col_uang else db.columns[-1]
    vals=ws_absen.get_all_values()
    absen=pd.DataFrame([r[:13] for r in vals[1:]], columns=HEADER) if len(vals)>1 else pd.DataFrame(columns=HEADER)
    if not absen.empty:
        absen['ID KARYAWAN']=absen['ID KARYAWAN'].astype(str).str.zfill(8)
        absen['TGL_DT']=pd.to_datetime(absen['TANGGAL'], errors='coerce')
        absen['JAM LEMBUR']=pd.to_numeric(absen['JAM LEMBUR'], errors='coerce').fillna(0)
    return db, absen, col_uang
db_df, absen_df, COL_UANG=load()

def get_periode(b,t,mode):
    if mode=="21-20 Payroll": return (date(t-1,12,21), date(t,1,20)) if b==1 else (date(t,b-1,21), date(t,b,20))
    return date(t,b,1), date(t,b,calendar.monthrange(t,b)[1])

def upsert(id_kar, masuk_dt, pulang_dt, nama, status="H"):
    if pulang_dt<masuk_dt: pulang_dt+=timedelta(days=1)
    total=(pulang_dt-masuk_dt).total_seconds()/3600
    jam_float=total-1 if total>6 else total
    tgl_str=masuk_dt.strftime('%Y-%m-%d')
    if not absen_df[(absen_df['ID KARYAWAN']==id_kar)&(absen_df['TANGGAL']==tgl_str)].empty:
        st.error("Sudah absen hari ini - 1 hari 1x! Edit di Google Sheet")
        return False
    jk,jl,l15,l20=hitung_lembur(jam_float, masuk_dt.weekday()==5, masuk_dt.weekday()==6, tgl_str in LIBUR, status)
    shift=f"H-S1" if 7<=masuk_dt.hour<=14 else f"H-S2" if 15<=masuk_dt.hour<=21 else "H-S3"
    ket="GANTI HARI" if status=="GH" else "GANTI HARI SABTU" if status=="GHS" else "LIBUR" if tgl_str in LIBUR else "MINGGU" if masuk_dt.weekday()==6 else "SABTU" if masuk_dt.weekday()==5 else "MASUK"
    try: uang=str(db_df[db_df['ID KARYAWAN']==id_kar][COL_UANG].values[0])
    except: uang="0"
    row=[id_kar,nama,tgl_str,masuk_dt.strftime('%H:%M:%S'),pulang_dt.strftime('%H:%M:%S'),jk,jl,l15,l20,shift,ket,"H" if status in ["GH","GHS"] else status,uang]
    ws_absen.insert_row(row,2); load.clear(); return True

# 3 TAB SIMPLE
tab1, tab2, tab3 = st.tabs(["👆 ABSEN", "📋 REKAP", "💰 GAJI - RUMUS 5.7JT"])

with tab1:
    id_in=st.text_input("ID", "01213027").zfill(8)
    nama=db_df[db_df['ID KARYAWAN']==id_in]['NAMA KARYAWAN'].values[0] if id_in in db_df['ID KARYAWAN'].values else ""
    if nama: st.success(nama)
    c1,c2=st.columns(2)
    tgl=c1.date_input("Tgl", datetime.now())
    status=c2.selectbox("Status", ["H","GH","GHS","I","S","A"])
    c3,c4=st.columns(2)
    jm=c3.time_input("Masuk", datetime.now().time())
    jp=c4.time_input("Pulang", datetime.now().time())
    if st.button("SIMPAN", type="primary", use_container_width=True, disabled=not nama):
        if upsert(id_in, datetime.combine(tgl,jm), datetime.combine(tgl,jp), nama, status):
            st.success("Berhasil"); st.balloons(); st.rerun()

with tab2:
    mode=st.radio("Periode", ["21-20 Payroll","Bulan Kalender"], horizontal=True)
    bln=st.selectbox("Bulan", range(1,13), index=datetime.now().month-1)
    thn=st.number_input("Tahun", 2020,2030, datetime.now().year)
    awal,akhir=get_periode(bln,thn,mode)
    st.info(f"{awal} s/d {akhir}")
    df_f=absen_df[(absen_df['TGL_DT']>=pd.to_datetime(awal))&(absen_df['TGL_DT']<=pd.to_datetime(akhir))] if not absen_df.empty else pd.DataFrame()
    st.dataframe(df_f, use_container_width=True)

with tab3:
    st.subheader("RUMUS GAJI GABUNG NEXA")
    mode_g=st.radio("Mode Gaji", ["21-20 Payroll","Bulan Kalender"], horizontal=True, key="mg")
    bln_g=st.selectbox("Bulan Gaji", range(1,13), index=datetime.now().month-1, key="bg")
    thn_g=st.number_input("Tahun Gaji", 2020,2030, datetime.now().year, key="tg")
    awal_g,akhir_g=get_periode(bln_g,thn_g,mode_g)
    st.info(f"Periode Gaji: {awal_g} s/d {akhir_g}")

    id_g=st.selectbox("Karyawan", db_df['ID KARYAWAN'].tolist() if not db_df.empty else ["01213027"])
    df_g=absen_df[(absen_df['ID KARYAWAN']==id_g)&(absen_df['TGL_DT']>=pd.to_datetime(awal_g))&(absen_df['TGL_DT']<=pd.to_datetime(akhir_g))] if not absen_df.empty else pd.DataFrame()

    if not df_g.empty:
        hadir=len(df_g[df_g['STATUS']=='H']) # GH/GHS sudah jadi H
        total_lembur=df_g['JAM LEMBUR'].sum()
        shift_malam=len(df_g[df_g['SHIFT'].astype(str).str.contains('S2|S3', na=False)])
        hari_lembur=len(df_g[df_g['JAM LEMBUR']>0])

        # RUMUS GAJI 5.781.289 YANG KEMARIN
        gaji_pokok=5252909
        uang_makan=hadir*9500
        uang_lembur=total_lembur*30000
        uang_shift=shift_malam*2187
        uang_makan_lembur=hari_lembur*9500
        total_pend=gaji_pokok+50000+uang_makan+uang_lembur+uang_shift+uang_makan_lembur+3500+12606+15758+194357+105058+210116
        total_pot=12606+15758+194357+105058+210116+105058+52529+52529
        total_gaji=total_pend-total_pot

        c1,c2,c3,c4=st.columns(4)
        c1.metric("Hadir", f"{hadir} Hari")
        c2.metric("Lembur NEXA", f"{total_lembur} Jam (G=J*1.5)")
        c3.metric("Shift", f"{shift_malam} Hari")
        c4.metric("TOTAL GAJI", f"Rp {int(total_gaji):,}")

        st.write(f"Rumus: Pokok {gaji_pokok:,} + Makan {hadir}x9500={uang_makan:,} + Lembur {total_lembur}x30000={int(uang_lembur):,} + Shift {shift_malam}x2187={uang_shift:,}")

        if st.button("🚀 UPDATE KE SHEET DATA GAJI", type="primary", use_container_width=True):
            ws_gaji.batch_update([
                {'range': 'B5', 'values': [[f"{hadir} Hari x 9500"]]},
                {'range': 'C5', 'values': [[int(uang_makan)]]},
                {'range': 'B7', 'values': [[f"{total_lembur} Jam x 30000"]]},
                {'range': 'C7', 'values': [[int(uang_lembur)]]},
                {'range': 'B8', 'values': [[f"{shift_malam} Hari x 2187"]]},
                {'range': 'C8', 'values': [[int(uang_shift)]]},
                {'range': 'B9', 'values': [[f"{hari_lembur} Hari x 9500"]]},
                {'range': 'C9', 'values': [[int(uang_makan_lembur)]]},
                {'range': 'C17', 'values': [[int(total_pend)]]},
                {'range': 'E17', 'values': [[int(total_pot)]]},
                {'range': 'C19', 'values': [[int(total_gaji)]]},
            ])
            st.success(f"Sheet DATA GAJI jadi Rp {int(total_gaji):,} - cek Google Sheet mu, udah gak #ERROR! lagi")
            st.balloons()
    else:
        st.warning("Belum ada absen di periode ini")
