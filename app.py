import streamlit as st, gspread, pandas as pd, requests, math, calendar
from datetime import datetime, timedelta, date
from google.oauth2.service_account import Credentials
from icalendar import Calendar

st.set_page_config(page_title="NEXA V15", layout="wide")
st.markdown("<h2>🛰️ NEXA V15 - ABSEN + GAJI + PERIODE</h2><p style='color:#9CA3AF;font-size:12px'>1 HARI 1 ABSEN | 22:00=S3 | PERIODE 21-20 | G=H*1.5+I*2.0</p>", unsafe_allow_html=True)

PASSWORD_ADMIN = "admin123"
ICS_URL = "https://calendar.google.com/calendar/ical/id.indonesian%23holiday%40group.v.calendar.google.com/public/basic.ics"

@st.cache_resource
def connect_gsheet():
    scope = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(creds)
    sh = client.open("REKAP")
    return sh.worksheet("REKAP ABSENSI"), sh.worksheet("DATABASE KARYAWAN")
ws_absen, ws_db = connect_gsheet()

@st.cache_data(ttl=86400)
def get_libur():
    try:
        r=requests.get(ICS_URL,timeout=10)
        cal=Calendar.from_ical(r.text)
        libur={}
        for c in cal.walk():
            if c.name=="VEVENT":
                s=c.get('dtstart').dt
                if hasattr(s,'strftime'): s=s.strftime('%Y-%m-%d')
                libur[s]=str(c.get('summary'))
        return libur
    except: return {}
LIBUR_NASIONAL=get_libur()
HEADER=['ID KARYAWAN','NAMA KARYAWAN','TANGGAL','JAM MASUK','JAM PULANG','JAM KERJA','JAM LEMBUR','LEMBUR 1.5','LEMBUR 2.0','SHIFT','KETERANGAN','STATUS','UANG SHIFT']

def hitung_lembur_bulat(jam_total_float, is_sabtu=False, is_minggu=False, is_merah=False, status="H"):
    try: jam_total_float=float(jam_total_float or 0)
    except: jam_total_float=0.0
    jam_total_float=math.floor(jam_total_float+0.5)
    if jam_total_float<=0: return "0.00","0.00","0.00","0.00"
    if status=="GH": return "7.00","0.00","0.00","0.00"
    if status=="GHS": return "5.00","0.00","0.00","0.00"
    if is_sabtu:
        if jam_total_float<=5: return "5.00","0.00","0.00","0.00"
        sisa=jam_total_float-5
        l15=1 if sisa>=1 else sisa
        l20=sisa-1 if sisa>1 else 0
        jl=l15*1.5+l20*2.0
        return "5.00",f"{jl:.2f}",f"{l15:.2f}",f"{l20:.2f}"
    if is_minggu or is_merah:
        return "0.00",f"{jam_total_float*2:.2f}","0.00",f"{jam_total_float:.2f}"
    if jam_total_float<=7: return f"{jam_total_float:.2f}","0.00","0.00","0.00"
    sisa=jam_total_float-7
    l15=1 if sisa>=1 else sisa
    l20=sisa-1 if sisa>1 else 0
    jl=l15*1.5+l20*2.0
    return "7.00",f"{jl:.2f}",f"{l15:.2f}",f"{l20:.2f}"

@st.cache_data(ttl=60)
def load_data():
    db=pd.DataFrame(ws_db.get_all_records())
    db['ID KARYAWAN']=db['ID KARYAWAN'].astype(str).str.zfill(8)
    col_uang=None
    for c in db.columns:
        if 'SHIFT' in c.upper() and 'UANG' in c.upper(): col_uang=c
    if not col_uang: col_uang=db.columns[-1]
    vals=ws_absen.get_all_values()
    if len(vals)>1:
        data=[r[:13] for r in vals[1:]]
        absen=pd.DataFrame(data,columns=HEADER) if data else pd.DataFrame(columns=HEADER)
    else: absen=pd.DataFrame(columns=HEADER)
    if not absen.empty:
        absen['ID KARYAWAN']=absen['ID KARYAWAN'].astype(str).str.zfill(8)
        absen['TGL_DT']=pd.to_datetime(absen['TANGGAL'],format='%Y-%m-%d',errors='coerce')
    return db,absen,col_uang
db_df,absen_df,COL_UANG_SHIFT=load_data()

def get_uang_shift(id_kar, shift, jam_lembur_float=0):
    try:
        v=db_df[db_df['ID KARYAWAN']==id_kar][COL_UANG_SHIFT].values[0]
        v=str(v).replace('Rp','').replace('.','').replace(',','').strip()
        if v=='' or v.lower()=='nan': v="0"
    except: v="0"
    if v=="0": return "0"
    if jam_lembur_float>0: return v
    if not any(x in str(shift).upper() for x in ['S2','S3','LS1','LS2']): return "0"
    return v

def cek_shift(masuk_dt,jam_float,ket,status):
    if 'LIBUR' in ket and status not in ["GH","GHS"]: return 'SL'
    if status in ['A','I','S','C','TL','GH','GHS','L']: return status
    if jam_float==0: return '-'
    hm=masuk_dt.hour
    if 7 <= hm <= 14: base='S1'
    elif 15 <= hm <= 21: base='S2'
    else: base='S3'
    if jam_float >= 11.5: return f"{status}-LS1" if base=='S1' else f"{status}-LS2"
    return f"{status}-{base}"

def cek_keterangan(tgl_dt,jm_str="",jp_str="",jam_float=0,status="H"):
    tgl_str=tgl_dt.strftime('%Y-%m-%d')
    if tgl_str in LIBUR_NASIONAL and status not in ["GH","GHS"]: return "LIBUR: "+LIBUR_NASIONAL[tgl_str]
    if jm_str and jp_str and jam_float>0:
        if status=="GH": return "GANTI HARI"
        if status=="GHS": return "GANTI HARI SABTU"
        return "MASUK"
    if status in ['A','I','S','C','TL','GH','GHS','L']: return {"A":"ALFA","I":"IZIN","S":"SAKIT","C":"CUTI","TL":"TUKAR LIBUR","GH":"GANTI HARI","GHS":"GANTI HARI SABTU","L":"LIBUR"}[status]
    if tgl_dt.weekday()==6: return "MINGGU"
    if tgl_dt.weekday()==5: return "SABTU"
    return "KERJA" if jam_float>0 else "TIDAK MASUK"

def hitung(masuk_dt,pulang_dt,status):
    if pulang_dt<masuk_dt: pulang_dt+=timedelta(days=1)
    total=(pulang_dt-masuk_dt).total_seconds()/3600
    is_sabtu = masuk_dt.weekday()==5
    jam_float = total-1.0 if total>6.0 else total if is_sabtu or status in ["GH","GHS"] else (total-1.0 if total>=6.0 else total)
    if jam_float<0: jam_float=0
    tgl_str=masuk_dt.strftime('%Y-%m-%d')
    jk,jl,l15,l20=hitung_lembur_bulat(jam_float, masuk_dt.weekday()==5, masuk_dt.weekday()==6, tgl_str in LIBUR_NASIONAL, status)
    ket=cek_keterangan(masuk_dt, masuk_dt.strftime('%H:%M:%S'), pulang_dt.strftime('%H:%M:%S'), jam_float, status)
    shift=cek_shift(masuk_dt, jam_float, ket, status)
    return jk,jl,l15,l20,shift,ket,masuk_dt.strftime('%H:%M:%S'),pulang_dt.strftime('%H:%M:%S')

def upsert_absen(id_kar,masuk_dt,pulang_dt,nama,status="H",allow_overwrite=False):
    id_kar=id_kar.zfill(8)
    tgl_str=masuk_dt.strftime('%Y-%m-%d')
    existing=absen_df[(absen_df['ID KARYAWAN']==id_kar)&(absen_df['TANGGAL']==tgl_str)]
    if not existing.empty and not allow_overwrite: return False
    jk,jl,l1,l2,shift,ket,jm,jp=hitung(masuk_dt,pulang_dt,status)
    if status in ['A','I','S','C','L','TL'] and status not in ["GH","GHS"]:
        jm="";jp="";jk=jl=l1=l2="0.00"; shift='SL' if tgl_str in LIBUR_NASIONAL else status; ket=cek_keterangan(masuk_dt,"","",0,status); uang="0"
    else:
        try: jl_f=float(jl)
        except: jl_f=0
        uang=get_uang_shift(id_kar, shift, jl_f)
    row=[id_kar,nama,tgl_str,jm,jp,jk,jl,l1,l2,shift,ket,status,uang]
    if not existing.empty:
        rn=existing.index[0]+2
        ws_absen.update(f'A{rn}:M{rn}',[row])
    else: ws_absen.insert_row(row,2)
    load_data.clear()
    return True

# === HELPER PERIODE ===
def get_periode(bulan,tahun,mode):
    if mode=="Bulan Kalender":
        awal=date(tahun,bulan,1)
        akhir=date(tahun,bulan,calendar.monthrange(tahun,bulan)[1])
    elif mode=="21-20 Payroll":
        if bulan==1:
            awal=date(tahun-1,12,21)
            akhir=date(tahun,1,20)
        else:
            awal=date(tahun,bulan-1,21)
            akhir=date(tahun,bulan,20)
    else:
        awal=date(tahun,bulan,1)
        akhir=date(tahun,bulan,calendar.monthrange(tahun,bulan)[1])
    return awal, akhir

tab1, tab2, tab3, tab4, tab5 = st.tabs(["ABSEN","EDIT","ADMIN","REKAP","GAJI"])

with tab1:
    st.write("ABSEN - 1 HARI 1X")
    id_in=st.text_input("ID ABSEN").strip().zfill(8)
    nama=""
    if id_in and id_in in db_df['ID KARYAWAN'].values:
        nama=db_df[db_df['ID KARYAWAN']==id_in]['NAMA KARYAWAN'].values[0]
        st.success(nama)
    tgl=st.date_input("Tanggal",datetime.now())
    c1,c2=st.columns(2)
    with c1:
        jm=st.time_input("Masuk",datetime.now().time())
        status_pilih=st.selectbox("Status", ["H","GH","GHS","TL","I","S","C","A"])
    with c2:
        jp=st.time_input("Pulang",datetime.now().time())
    sudah=False
    if id_in and nama:
        cek=absen_df[(absen_df['ID KARYAWAN']==id_in)&(absen_df['TANGGAL']==tgl.strftime('%Y-%m-%d'))]
        if not cek.empty:
            sudah=True
            st.error(f"SUDAH ABSEN {cek.iloc[0]['JAM MASUK']}-{cek.iloc[0]['JAM PULANG']} {cek.iloc[0]['SHIFT']}")
    if st.button("SIMPAN",type="primary",use_container_width=True,disabled=not nama or sudah):
        ok=upsert_absen(id_in, datetime.combine(tgl,jm), datetime.combine(tgl,jp), nama, status_pilih, False)
        if not ok: st.error("SUDAH ABSEN")
        else: st.success("BERHASIL"); st.balloons(); st.rerun()

with tab2:
    st.write("EDIT")
    if "login" not in st.session_state: st.session_state.login=False
    if not st.session_state.login:
        pw=st.text_input("Password",type="password")
        if st.button("LOGIN"):
            if pw==PASSWORD_ADMIN: st.session_state.login=True; st.rerun()
    else:
        if st.button("LOGOUT"): st.session_state.login=False; st.rerun()
        id_edit=st.text_input("ID EDIT").strip().zfill(8)
        if id_edit and id_edit in db_df['ID KARYAWAN'].values:
            data_kar=absen_df[absen_df['ID KARYAWAN']==id_edit]
            if not data_kar.empty:
                pilih_tgl=st.selectbox("Tanggal", data_kar.sort_values('TGL_DT',ascending=False)['TANGGAL'].tolist())
                row=data_kar[data_kar['TANGGAL']==pilih_tgl].iloc[0]
                st.write(f"{row['JAM MASUK']}-{row['JAM PULANG']} {row['SHIFT']}")
                c1,c2=st.columns(2)
                with c1:
                    tgl_e=st.date_input("Tgl Edit", pd.to_datetime(row['TANGGAL']))
                    jm_e=st.time_input("Masuk Edit", datetime.strptime(row['JAM MASUK'],'%H:%M:%S').time() if row['JAM MASUK'] else datetime.now().time())
                with c2:
                    jp_e=st.time_input("Pulang Edit", datetime.strptime(row['JAM PULANG'],'%H:%M:%S').time() if row['JAM PULANG'] else datetime.now().time())
                    st_e=st.selectbox("Status Baru", ["H","GH","GHS","TL","I","S","C","A","L"])
                if st.button("UPDATE",type="primary",use_container_width=True):
                    upsert_absen(id_edit, datetime.combine(tgl_e,jm_e), datetime.combine(tgl_e,jp_e), row['NAMA KARYAWAN'], st_e, True)
                    st.success("Updated"); st.rerun()

with tab3:
    st.write("ADMIN")
    if st.button("CALIBRATION",type="primary",use_container_width=True):
        with st.spinner("Fixing..."):
            vals=ws_absen.get_all_values()
            for i,r in enumerate(vals[1:], start=2):
                try:
                    if len(r)<5 or not r[3] or not r[4]: continue
                    tgl=datetime.strptime(r[2], '%Y-%m-%d')
                    masuk=datetime.strptime(r[3], '%H:%M:%S')
                    pulang=datetime.strptime(r[4], '%H:%M:%S')
                    md=datetime.combine(tgl, masuk.time())
                    pd_=datetime.combine(tgl, pulang.time())
                    if pd_<md: pd_+=timedelta(days=1)
                    total=(pd_-md).total_seconds()/3600
                    stat=r[11] if len(r)>11 else "H"
                    id_kar=r[0].zfill(8)
                    is_sabtu=tgl.weekday()==5
                    is_minggu=tgl.weekday()==6
                    jam_float=total-1.0 if total>6.0 else total if is_sabtu else (total-1.0 if total>=6.0 else total)
                    jk,jl,l15,l20=hitung_lembur_bulat(jam_float, is_sabtu, is_minggu, r[2] in LIBUR_NASIONAL, stat)
                    try: jl_f=float(jl)
                    except: jl_f=0
                    hm=masuk.hour
                    base='S1' if 7<=hm<=14 else 'S2' if 15<=hm<=21 else 'S3'
                    shift_baru = stat+"-LS1" if jam_float>=11.5 and base=='S1' else stat+"-LS2" if jam_float>=11.5 else stat+"-"+base
                    uang_baru=get_uang_shift(id_kar, shift_baru, jl_f)
                    ket_baru=cek_keterangan(tgl, r[3], r[4], jam_float, stat)
                    ws_absen.update(f'F{i}:M{i}', [[jk,jl,l15,l20,shift_baru,ket_baru,stat,uang_baru]])
                except: pass
            st.success("DONE"); load_data.clear(); st.balloons(); st.rerun()

with tab4:
    st.write("### REKAP DENGAN PERIODE")
    mode_r = st.radio("Mode Rekap", ["Bulan Kalender","21-20 Payroll","Custom"], horizontal=True, key="mode_r")
    c1,c2,c3=st.columns(3)
    with c1: bulan_r=st.selectbox("Bulan", list(range(1,13)), index=datetime.now().month-1, key="bulan_r")
    with c2: tahun_r=st.number_input("Tahun", 2020, 2030, datetime.now().year, key="tahun_r")
    with c3:
        if mode_r=="Custom":
            awal_r=st.date_input("Dari", date(tahun_r,bulan_r,1), key="awal_r")
            akhir_r=st.date_input("Sampai", date(tahun_r,bulan_r,calendar.monthrange(tahun_r,bulan_r)[1]), key="akhir_r")
        else:
            awal_r, akhir_r = get_periode(bulan_r, tahun_r, mode_r)
            st.write(f"Periode")
            st.success(f"{awal_r} s/d {akhir_r}")
    if not absen_df.empty:
        df_f = absen_df[(absen_df['TGL_DT']>=pd.to_datetime(awal_r))&(absen_df['TGL_DT']<=pd.to_datetime(akhir_r))]
        st.write(f"Total {len(df_f)} data periode {awal_r} - {akhir_r}")
        st.dataframe(df_f, use_container_width=True, height=500)
        csv = df_f.to_csv(index=False).encode('utf-8')
        st.download_button("DOWNLOAD CSV PERIODE", csv, f"rekap_{awal_r}_{akhir_r}.csv", "text/csv", use_container_width=True)

with tab5:
    st.write("### GAJI V14 - AUTO DARI ABSEN + PERIODE")
    mode_g = st.radio("Mode Gaji", ["Bulan Kalender","21-20 Payroll","Custom"], horizontal=True, key="mode_g")
    c1,c2=st.columns(2)
    with c1: bulan_g=st.selectbox("Bulan Gaji", list(range(1,13)), index=datetime.now().month-1, key="bulan_g")
    with c2: tahun_g=st.number_input("Tahun Gaji", 2020, 2030, datetime.now().year, key="tahun_g")
    if mode_g=="Custom":
        cc1,cc2=st.columns(2)
        with cc1: awal_g=st.date_input("Dari Tgl Gaji", date(tahun_g,bulan_g,1), key="awal_g")
        with cc2: akhir_g=st.date_input("Sampai Tgl Gaji", date(tahun_g,bulan_g,calendar.monthrange(tahun_g,bulan_g)[1]), key="akhir_g")
    else:
        awal_g, akhir_g = get_periode(bulan_g, tahun_g, mode_g)
    st.info(f"Periode Gaji: {awal_g} s/d {akhir_g} ({(akhir_g-awal_g).days+1} hari)")
    id_gaji=st.selectbox("Pilih Karyawan", db_df['ID KARYAWAN'].tolist() if not db_df.empty else ["01213027"])
    if st.button("HITUNG REAL DARI ABSEN", type="primary", use_container_width=True):
        if not absen_df.empty:
            df_g = absen_df[(absen_df['ID KARYAWAN']==id_gaji)&(absen_df['TGL_DT']>=pd.to_datetime(awal_g))&(absen_df['TGL_DT']<=pd.to_datetime(akhir_g))]
            st.success(f"Ditemukan {len(df_g)} hari kerja")
            st.dataframe(df_g, use_container_width=True)
            total_kerja = df_g['JAM KERJA'].astype(float).sum() if not df_g.empty else 0
            total_lembur = df_g['JAM LEMBUR'].astype(float).sum() if not df_g.empty else 0
            st.metric("Total Jam Kerja", f"{total_kerja:.2f}")
            st.metric("Total Jam Lembur (sudah x1.5 & x2)", f"{total_lembur:.2f}")
