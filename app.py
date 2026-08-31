import streamlit as st, gspread, pandas as pd, requests, math
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from icalendar import Calendar

st.set_page_config(page_title="NEXA v11.2.1", layout="wide")
st.markdown("<h2>🛰️ NEXA ATTENDANCE PRO</h2><p style='color:#9CA3AF;letter-spacing:3px;font-size:12px'>V11.2.1 FINAL - JAM LEMBUR = H*1.5 + I*2.0</p>", unsafe_allow_html=True)

PASSWORD_ADMIN="admin123"
ICS_URL="https://calendar.google.com/calendar/ical/id.indonesian%23holiday%40group.v.calendar.google.com/public/basic.ics"

@st.cache_resource
def connect_gsheet():
    scope=["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
    creds=Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client=gspread.authorize(creds)
    sh=client.open("REKAP")
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
        l20=jam_total_float
        jl=l20*2.0
        return "0.00",f"{jl:.2f}","0.00",f"{l20:.2f}"
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

def bulatkan_ke_jam_pas(dt): return dt.replace(second=0,microsecond=0)
def cek_keterangan(tgl_dt,jm_str="",jp_str="",jam_float=0,status="H"):
    tgl_str=tgl_dt.strftime('%Y-%m-%d')
    if tgl_str in LIBUR_NASIONAL and status not in ["GH","GHS"]: return f"LIBUR NASIONAL: {LIBUR_NASIONAL[tgl_str]}"
    if jm_str and jp_str and jam_float>0:
        if status=="GH": return "GANTI HARI"
        if status=="GHS": return "GANTI HARI SABTU"
        return "MASUK"
    if status in ['A','I','S','C','TL','GH','GHS','L']: return {"A":"ALFA","I":"IZIN","S":"SAKIT","C":"CUTI","TL":"TUKAR LIBUR","GH":"GANTI HARI","GHS":"GANTI HARI SABTU","L":"SHIFT LIBUR"}[status]
    if tgl_dt.weekday()==6: return "LIBUR MINGGU"
    if tgl_dt.weekday()==5: return "SABTU"
    return "HARI KERJA" if jam_float>0 else "TIDAK MASUK"
def cek_shift(masuk_dt,jam_float,ket,status):
    if 'LIBUR' in ket and status not in ["GH","GHS"]: return 'SL'
    if status in ['A','I','S','C','TL','GH','GHS','L']: return status
    if jam_float==0: return '-'
    hm=masuk_dt.hour
    if hm>=19: return f"{status}-LS2"
    if jam_float>=11.5: sc='LS1'
    else:
        if 7<=hm<15: sc='S1'
        elif 15<=hm<23: sc='S2'
        else: sc='S3'
    return f"{status}-{sc}"
def hitung(masuk_dt,pulang_dt,status):
    masuk_dt=bulatkan_ke_jam_pas(masuk_dt)
    pulang_dt=bulatkan_ke_jam_pas(pulang_dt)
    if pulang_dt<masuk_dt: pulang_dt+=timedelta(days=1)
    total=(pulang_dt-masuk_dt).total_seconds()/3600
    is_sabtu_flag = masuk_dt.weekday()==5
    jam_float = total - 1.0 if total > 6.0 else total if is_sabtu_flag or status in ["GH","GHS"] else (total - 1.0 if total >= 6.0 else total)
    if jam_float<0: jam_float=0
    tgl_str=masuk_dt.strftime('%Y-%m-%d')
    jk,jl,l15,l20=hitung_lembur_bulat(jam_float, masuk_dt.weekday()==5, masuk_dt.weekday()==6, tgl_str in LIBUR_NASIONAL, status)
    ket=cek_keterangan(masuk_dt, masuk_dt.strftime('%H:%M:%S'), pulang_dt.strftime('%H:%M:%S'), jam_float, status)
    shift=cek_shift(masuk_dt, jam_float, ket, status)
    return jk,jl,l15,l20,shift,ket,masuk_dt.strftime('%H:%M:%S'),pulang_dt.strftime('%H:%M:%S')
def upsert_absen(id_kar,masuk_dt,pulang_dt,nama,status="H",sudah_pulang=True):
    id_kar=id_kar.zfill(8)
    tgl_str=masuk_dt.strftime('%Y-%m-%d')
    if not sudah_pulang:
        jk=jl=l1=l2="0.00"; jm=masuk_dt.strftime('%H:%M:%S'); jp=""; shift="-"; ket="BELUM PULANG"; uang="0"
    else:
        jk,jl,l1,l2,shift,ket,jm,jp=hitung(masuk_dt,pulang_dt,status)
        if status in ['A','I','S','C','L','TL'] and status not in ["GH","GHS"]:
            jm="";jp="";jk=jl=l1=l2="0.00"; shift='SL' if tgl_str in LIBUR_NASIONAL else status; ket=cek_keterangan(masuk_dt,"","",0,status); uang="0"
        else:
            try: jl_f=float(jl)
            except: jl_f=0
            uang=get_uang_shift(id_kar, shift, jl_f)
    row=[id_kar,nama,tgl_str,jm,jp,jk,jl,l1,l2,shift,ket,status,uang]
    existing=absen_df[(absen_df['ID KARYAWAN']==id_kar)&(absen_df['TANGGAL']==tgl_str)]
    if not existing.empty:
        rn=existing.index[0]+2
        ws_absen.update(f'A{rn}:M{rn}',[row])
    else: ws_absen.insert_row(row,2)
    load_data.clear()

# TABS HARUS DI LUAR TRY
tab_absen, tab_edit, tab_admin, tab_rekap = st.tabs(["📝 ABSEN","✏️ EDIT","⚙️ ADMIN","📊 REKAP"])

with tab_absen:
    st.write("### ABSEN")
    id_in=st.text_input("ID Karyawan ABSEN").strip().zfill(8)
    nama=""
    if id_in and id_in in db_df['ID KARYAWAN'].values:
        nama=db_df[db_df['ID KARYAWAN']==id_in]['NAMA KARYAWAN'].values[0]
        st.success(f"✅ {nama}")
    tgl=st.date_input("Tanggal",datetime.now())
    c1,c2=st.columns(2)
    with c1:
        jm=st.time_input("Jam Masuk",datetime.now().time())
        status_pilih=st.selectbox("Status", ["H","GH","GHS","TL","I","S","C","A"], key="status_absen")
    with c2:
        jp=st.time_input("Jam Pulang",datetime.now().time())
    if st.button("💾 SIMPAN ABSEN",type="primary",use_container_width=True,disabled=not nama):
        upsert_absen(id_in, datetime.combine(tgl,jm), datetime.combine(tgl,jp), nama, status_pilih, True)
        st.success("Saved"); st.rerun()

with tab_edit:
    st.write("### EDIT")
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
                st.write(f"{row['JAM MASUK']}-{row['JAM PULANG']} | {row['JAM LEMBUR']}")
                c1,c2=st.columns(2)
                with c1:
                    tgl_e=st.date_input("Tgl", pd.to_datetime(row['TANGGAL']))
                    jm_e=st.time_input("Masuk", datetime.strptime(row['JAM MASUK'],'%H:%M:%S').time() if row['JAM MASUK'] else datetime.now().time())
                with c2:
                    jp_e=st.time_input("Pulang", datetime.strptime(row['JAM PULANG'],'%H:%M:%S').time() if row['JAM PULANG'] else datetime.now().time())
                    st_e=st.selectbox("Status", ["H","GH","GHS","TL","I","S","C","A","L"], index=0)
                if st.button("UPDATE",type="primary",use_container_width=True):
                    upsert_absen(id_edit, datetime.combine(tgl_e,jm_e), datetime.combine(tgl_e,jp_e), row['NAMA KARYAWAN'], st_e, True)
                    st.success("Updated"); st.rerun()

with tab_admin:
    st.write("### ⚙️ System Calibration Center")
    st.info("G = H*1.5 + I*2.0 | GH 7 jam no lembur | GHS 5 jam no lembur | Lembur dapat uang shift")
    if st.button("🚀 ONE CLICK CALIBRATION", type="primary", use_container_width=True):
        with st.spinner("Fixing all..."):
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
                    if stat=="GH":
                        ws_absen.update(f'F{i}:M{i}', [["7.00","0.00","0.00","0.00","GH","GANTI HARI","GH","0"]])
                    elif stat=="GHS":
                        ws_absen.update(f'F{i}:M{i}', [["5.00","0.00","0.00","0.00","GHS","GANTI HARI SABTU","GHS","0"]])
                    else:
                        is_sabtu=tgl.weekday()==5
                        is_minggu=tgl.weekday()==6
                        jam_float=total-1.0 if total>6.0 else total if is_sabtu else (total-1.0 if total>=6.0 else total)
                        jk,jl,l15,l20=hitung_lembur_bulat(jam_float, is_sabtu, is_minggu, r[2] in LIBUR_NASIONAL, stat)
                        try: jl_f=float(jl)
                        except: jl_f=0
                        shift_lama=r[9] if len(r)>9 else "-"
                        uang_baru=get_uang_shift(id_kar, shift_lama, jl_f)
                        ws_absen.update(f'F{i}:M{i}', [[jk,jl,l15,l20,shift_lama,r[10] if len(r)>10 else "MASUK",stat,uang_baru]])
                except Exception as e:
                    st.write(f"Error row {i}: {e}")
            st.success("✅ DONE! G = H*1.5 + I*2.0")
            load_data.clear()
            st.balloons()
            st.rerun()

with tab_rekap:
    st.dataframe(absen_df, use_container_width=True, height=600)
