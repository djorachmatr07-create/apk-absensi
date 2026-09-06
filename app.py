import streamlit as st, gspread, pandas as pd, requests, math, calendar
from datetime import datetime, timedelta, date
from google.oauth2.service_account import Credentials
from icalendar import Calendar

st.set_page_config(page_title="NEXA V16.2 AUTO 23.59", layout="wide", page_icon="🛰️")
st.markdown("<h2>🛰️ NEXA V16.2 AUTO 23.59</h2><p style='color:#9CA3AF;font-size:12px'>AUTO LIBUR JAM 23.59 | TGL MASUK - TGL PULANG | EDITABLE</p>", unsafe_allow_html=True)

PASSWORD_ADMIN = "admin123"
ICS_URL = "https://calendar.google.com/calendar/ical/id.indonesian%23holiday%40group.v.calendar.google.com/public/basic.ics"

@st.cache_resource
def connect_gsheet():
    scope = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(creds)
    sh = client.open("REKAP")
    return sh.worksheet("REKAP ABSENSI"), sh.worksheet("DATABASE KARYAWAN"), sh.worksheet("DATA GAJI")
ws_absen, ws_db, ws_gaji = connect_gsheet()

@st.cache_data(ttl=86400)
def get_libur():
    try:
        r = requests.get(ICS_URL, timeout=10)
        cal = Calendar.from_ical(r.text)
        libur = {}
        for c in cal.walk():
            if c.name == "VEVENT":
                s = c.get('dtstart').dt
                if hasattr(s, 'strftime'): s = s.strftime('%Y-%m-%d')
                libur[s] = str(c.get('summary'))
        return libur
    except: return {}
LIBUR_NASIONAL = get_libur()
HEADER = ['ID KARYAWAN','NAMA KARYAWAN','TANGGAL MASUK','JAM MASUK','TANGGAL PULANG','JAM PULANG','JAM KERJA','JAM LEMBUR','LEMBUR 1.5','LEMBUR 2.0','SHIFT','KETERANGAN','STATUS','UANG SHIFT']

# === AUTO CLOSE JAM 23.59 - FIX TGL 6 MINGGU ===
def auto_close_hari_bolong():
    try:
        vals = ws_absen.get_all_values()
        if len(vals) < 2: return
        tgl_existing = [r[2] for r in vals[1:] if len(r)>2]
        today = date.today()
        # cek dari 2026-08-01 sampai kemarin biar tgl 6 keisi
        start = date(2026, 8, 1)
        d = start
        while d < today:
            d_str = d.strftime('%Y-%m-%d')
            # kalau sudah ada skip
            if d_str not in tgl_existing:
                # hanya auto jika sudah lewat 23.59 (d < today)
                is_minggu = d.weekday()==6
                is_merah = d_str in LIBUR_NASIONAL
                if is_minggu:
                    row = ["01213027","RACHMAT RAHARDJO",d_str,"",d_str,"","0.00","0.00","0.00","0.00","L","MINGGU","L","0"]
                    ws_absen.insert_row(row, 2)
                elif is_merah:
                    row = ["01213027","RACHMAT RAHARDJO",d_str,"",d_str,"","0.00","0.00","0.00","0.00","SL",f"LIBUR NASIONAL {LIBUR_NASIONAL[d_str]}","L","0"]
                    ws_absen.insert_row(row, 2)
                elif d.weekday() < 5: # Senin-Jumat aja yang auto A
                    # kalau di SS mu yang 2026-08-19 TIDAK MASUK A itu udah ada, jadi gak duplikat
                    row = ["01213027","RACHMAT RAHARDJO",d_str,"",d_str,"","0.00","0.00","0.00","0.00","-","TIDAK MASUK","A","0"]
                    ws_absen.insert_row(row, 2)
            d += timedelta(days=1)
    except: pass

# PANGGIL OTOMATIS PAS APP DIBUKA - JADI JAM 23.59 AUTO MUNCUL
auto_close_hari_bolong()

def hitung_lembur_bulat(jam_float, is_sabtu=False, is_minggu=False, is_merah=False, status="H"):
    try: jam_float=float(jam_float or 0)
    except: jam_float=0.0
    jam_float=math.floor(jam_float+0.5)
    if jam_float<=0: return "0.00","0.00","0.00","0.00"
    if status in ["GH","GHS"]: return ("7.00","0.00","0.00","0.00") if status=="GH" else ("5.00","0.00","0.00","0.00")
    if is_sabtu:
        if jam_float<=5: return "5.00","0.00","0.00","0.00"
        sisa=jam_float-5; l15=1 if sisa>=1 else sisa; l20=sisa-1 if sisa>1 else 0; jl=l15*1.5+l20*2.0
        return "5.00",f"{jl:.2f}",f"{l15:.2f}",f"{l20:.2f}"
    if is_minggu or is_merah: return "0.00",f"{jam_float*2.0:.2f}","0.00",f"{jam_float:.2f}"
    if jam_float<=7: return f"{jam_float:.2f}","0.00","0.00","0.00"
    sisa=jam_float-7; l15=1 if sisa>=1 else sisa; l20=sisa-1 if sisa>1 else 0; jl=l15*1.5+l20*2.0
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
        data=[r[:14] for r in vals[1:]]
        absen=pd.DataFrame(data,columns=HEADER) if data else pd.DataFrame(columns=HEADER)
    else: absen=pd.DataFrame(columns=HEADER)
    if not absen.empty:
        absen['ID KARYAWAN']=absen['ID KARYAWAN'].astype(str).str.zfill(8)
        absen['TGL_DT']=pd.to_datetime(absen['TANGGAL MASUK'],format='%Y-%m-%d',errors='coerce')
        absen['JAM LEMBUR']=pd.to_numeric(absen['JAM LEMBUR'], errors='coerce').fillna(0)
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
    if 'LIBUR' in ket and status not in ["GH","GHS","H"]: return 'SL'
    if status in ['A','I','S','C','TL','L']: return status
    if jam_float==0: return '-'
    hm=masuk_dt.hour
    if 7 <= hm <= 14: base='S1'
    elif 15 <= hm <= 21: base='S2'
    else: base='S3'
    if jam_float >= 11.5: return f"H-LS1" if base=='S1' else f"H-LS2"
    return f"H-{base}"

def cek_keterangan(tgl_dt,jm_str="",jp_str="",jam_float=0,status="H"):
    tgl_str=tgl_dt.strftime('%Y-%m-%d')
    if tgl_str in LIBUR_NASIONAL and status not in ["GH","GHS","H"]: return "LIBUR: "+LIBUR_NASIONAL[tgl_str]
    if status=="GH": return "GANTI HARI"
    if status=="GHS": return "GANTI HARI SABTU"
    if jm_str and jp_str and jam_float>0: return "MASUK"
    if status in ['A','I','S','C','TL','L']: return {"A":"ALFA","I":"IZIN","S":"SAKIT","C":"CUTI","TL":"TUKAR LIBUR","L":"LIBUR"}[status]
    if tgl_dt.weekday()==6: return "MINGGU"
    if tgl_dt.weekday()==5: return "SABTU"
    return "KERJA" if jam_float>0 else "TIDAK MASUK"

def hitung_final(masuk_dt,pulang_dt,status_input):
    if pulang_dt < masuk_dt: pulang_dt += timedelta(days=1)
    total=(pulang_dt-masuk_dt).total_seconds()/3600
    is_sabtu = masuk_dt.weekday()==5
    jam_float = total-1.0 if total>6.0 else total if is_sabtu or status_input in ["GH","GHS"] else (total-1.0 if total>=6.0 else total)
    if jam_float<0: jam_float=0
    tgl_masuk_str=masuk_dt.strftime('%Y-%m-%d')
    status_final = "H" if status_input in ["GH","GHS","H"] else status_input
    if status_input=="GH": jk,jl,l15,l20="7.00","0.00","0.00","0.00"; ket="GANTI HARI"; hm=masuk_dt.hour; base='S1' if 7<=hm<=14 else 'S2' if 15<=hm<=21 else 'S3'; shift=f"H-{base}"
    elif status_input=="GHS": jk,jl,l15,l20="5.00","0.00","0.00","0.00"; ket="GANTI HARI SABTU"; shift="H-S1"
    else: jk,jl,l15,l20=hitung_lembur_bulat(jam_float, masuk_dt.weekday()==5, masuk_dt.weekday()==6, tgl_masuk_str in LIBUR_NASIONAL, status_input); ket=cek_keterangan(masuk_dt, masuk_dt.strftime('%H:%M:%S'), pulang_dt.strftime('%H:%M:%S'), jam_float, status_input); shift=cek_shift(masuk_dt, jam_float, ket, status_input)
    return jk,jl,l15,l20,shift,ket,status_final

def get_periode(bulan,tahun,mode):
    if mode=="Bulan Kalender": awal=date(tahun,bulan,1); akhir=date(tahun,bulan,calendar.monthrange(tahun,bulan)[1])
    elif mode=="21-20 Payroll":
        if bulan==1: awal=date(tahun-1,12,21); akhir=date(tahun,1,20)
        else: awal=date(tahun,bulan-1,21); akhir=date(tahun,bulan,20)
    else: awal=date(tahun,bulan,1); akhir=date(tahun,bulan,calendar.monthrange(tahun,bulan)[1])
    return awal, akhir

tab1, tab2, tab3, tab4, tab5 = st.tabs(["ABSEN","EDIT","ADMIN","REKAP","GAJI"])

with tab1:
    st.markdown("### ABSEN SIMPLE - BISA EDIT TGL/JAM")
    id_in=st.text_input("ID ABSEN", value="01213027").strip().zfill(8)
    nama=db_df[db_df['ID KARYAWAN']==id_in]['NAMA KARYAWAN'].values[0] if id_in in db_df['ID KARYAWAN'].values else ""
    if nama: st.success(f"👋 {nama}")
    if not nama: st.warning("Isi ID dulu")
    else:
        ubah_manual = st.checkbox("✏️ Ubah Tanggal & Jam Manual?", value=False)
        today_str = datetime.now().strftime('%Y-%m-%d')
        row_today = absen_df[(absen_df['ID KARYAWAN']==id_in)&(absen_df['TANGGAL MASUK']==today_str)] if not absen_df.empty else pd.DataFrame()
        if row_today.empty:
            # CEK APAKAH HARI INI SUDAH ADA AUTO LIBUR L?
            cek_auto = absen_df[(absen_df['ID KARYAWAN']==id_in)&(absen_df['TANGGAL MASUK']==today_str)&(absen_df['STATUS']=='L')]
            if not cek_auto.empty:
                st.info(f"📅 Hari ini {today_str} = {cek_auto.iloc[0]['KETERANGAN']} - Auto libur jam 23.59 kemarin")
            else:
                st.info(f"📅 Hari ini {today_str} belum absen")
                status_pilih=st.selectbox("Status", ["H","GH","GHS","I","S","A"], key="st_masuk")
                c1,c2=st.columns(2)
                if ubah_manual:
                    tgl_masuk_manual=c1.date_input("TANGGAL MASUK", value=date.today(), key="tgl_m")
                    jam_masuk_manual=c2.time_input("JAM MASUK", value=datetime.now().time(), key="jam_m")
                else:
                    tgl_masuk_manual=date.today(); jam_masuk_manual=datetime.now().time()
                    c1.write(f"TGL MASUK: {tgl_masuk_manual}"); c2.write(f"JAM: {jam_masuk_manual.strftime('%H:%M:%S')}")
                if st.button("🟢 ABSEN MASUK", type="primary", use_container_width=True):
                    masuk_dt=datetime.combine(tgl_masuk_manual, jam_masuk_manual)
                    cek_dup=absen_df[(absen_df['ID KARYAWAN']==id_in)&(absen_df['TANGGAL MASUK']==tgl_masuk_manual.strftime('%Y-%m-%d'))&(absen_df['JAM MASUK']!="")] if not absen_df.empty else pd.DataFrame()
                    if not cek_dup.empty: st.error(f"Sudah absen {tgl_masuk_manual}")
                    else:
                        # hapus dulu auto L jika ada
                        if not cek_auto.empty:
                            rn=cek_auto.index[0]+2; ws_absen.delete_rows(rn)
                        row=[id_in,nama,tgl_masuk_manual.strftime('%Y-%m-%d'),masuk_dt.strftime('%H:%M:%S'),"","","0.00","0.00","0.00","0.00","-","MASUK","H","0"]
                        ws_absen.insert_row(row,2); load_data.clear(); st.success("MASUK OK"); st.balloons(); st.rerun()
        else:
            r=row_today.iloc[0]
            if r['JAM PULANG']=="" or r['JAM PULANG']=="0.00" or r['JAM PULANG']=="0" or pd.isna(r['JAM PULANG']):
                # kalau status L (minggu) jangan tampil pulang
                if r['STATUS'] in ['L','A']:
                    st.success(f"✅ {r['TANGGAL MASUK']} = {r['KETERANGAN']} ({r['STATUS']})")
                else:
                    st.warning(f"✅ Masuk {r['TANGGAL MASUK']} {r['JAM MASUK']} - Belum Pulang")
                    c1,c2=st.columns(2)
                    if ubah_manual:
                        default_tgl_p=date.today()
                        try:
                            if datetime.now().time() < datetime.strptime(r['JAM MASUK'], '%H:%M:%S').time(): default_tgl_p=date.today()+timedelta(days=1)
                        except: pass
                        tgl_pulang_manual=c1.date_input("TANGGAL PULANG", value=default_tgl_p, key="tgl_p")
                        jam_pulang_manual=c2.time_input("JAM PULANG", value=datetime.now().time(), key="jam_p")
                    else:
                        tgl_pulang_manual=date.today(); jam_pulang_manual=datetime.now().time()
                        try:
                            if jam_pulang_manual < datetime.strptime(r['JAM MASUK'], '%H:%M:%S').time(): tgl_pulang_manual=date.today()+timedelta(days=1)
                        except: pass
                        c1.write(f"TGL PULANG: {tgl_pulang_manual}"); c2.write(f"JAM: {jam_pulang_manual.strftime('%H:%M:%S')}")
                    if st.button("🔴 ABSEN PULANG", type="primary", use_container_width=True):
                        try: masuk_dt=datetime.combine(datetime.strptime(r['TANGGAL MASUK'], '%Y-%m-%d').date(), datetime.strptime(r['JAM MASUK'], '%H:%M:%S').time())
                        except: masuk_dt=datetime.combine(date.today(), datetime.strptime(r['JAM MASUK'], '%H:%M:%S').time())
                        pulang_dt=datetime.combine(tgl_pulang_manual, jam_pulang_manual)
                        jk,jl,l15,l20,shift,ket,status_final=hitung_final(masuk_dt,pulang_dt,r['STATUS'])
                        uang=get_uang_shift(id_in, shift, float(jl) if jl else 0)
                        rn=row_today.index[0]+2
                        ws_absen.update(f'C{rn}:N{rn}', [[r['TANGGAL MASUK'],r['JAM MASUK'],tgl_pulang_manual.strftime('%Y-%m-%d'),jam_pulang_manual.strftime('%H:%M:%S'),jk,jl,l15,l20,shift,ket,status_final,uang]])
                        load_data.clear(); st.success(f"PULANG OK {jk} jam"); st.balloons(); st.rerun()
            else:
                st.success(f"✅ SELESAI: {r['TANGGAL MASUK']} {r['JAM MASUK']} -> {r['TANGGAL PULANG']} {r['JAM PULANG']} | {r['SHIFT']}")

with tab2:
    st.write("EDIT");
    if "login" not in st.session_state: st.session_state.login=False
    if not st.session_state.login:
        pw=st.text_input("Password",type="password")
        if st.button("LOGIN"):
            if pw==PASSWORD_ADMIN: st.session_state.login=True; st.rerun()
    else:
        if st.button("LOGOUT"): st.session_state.login=False; st.rerun()
        id_edit=st.text_input("ID EDIT").strip().zfill(8)
        if id_edit in db_df['ID KARYAWAN'].values:
            data_kar=absen_df[absen_df['ID KARYAWAN']==id_edit]
            if not data_kar.empty:
                pilih_tgl=st.selectbox("Tanggal Masuk", data_kar.sort_values('TGL_DT',ascending=False)['TANGGAL MASUK'].tolist())
                row=data_kar[data_kar['TANGGAL MASUK']==pilih_tgl].iloc[0]
                st.write(f"{row['TANGGAL MASUK']} {row['JAM MASUK']} -> {row['TANGGAL PULANG']} {row['JAM PULANG']} {row['SHIFT']}")
                c1,c2=st.columns(2)
                with c1: tgl_e=st.date_input("Tgl Masuk", pd.to_datetime(row['TANGGAL MASUK'])); jm_e=st.time_input("Masuk", datetime.strptime(row['JAM MASUK'],'%H:%M:%S').time() if row['JAM MASUK'] and row['JAM MASUK'] not in ["0.00","0",""] else datetime.now().time())
                with c2: tgl_pe=st.date_input("Tgl Pulang", pd.to_datetime(row['TANGGAL PULANG']) if row['TANGGAL PULANG'] and row['TANGGAL PULANG'] not in ["0.00","0",""] else pd.to_datetime(row['TANGGAL MASUK'])); jp_e=st.time_input("Pulang", datetime.strptime(row['JAM PULANG'],'%H:%M:%S').time() if row['JAM PULANG'] and row['JAM PULANG'] not in ["0.00","0",""] else datetime.now().time())
                st_e=st.selectbox("Status", ["H","GH","GHS","TL","I","S","C","A","L"])
                if st.button("UPDATE",type="primary",use_container_width=True):
                    masuk_dt=datetime.combine(tgl_e,jm_e); pulang_dt=datetime.combine(tgl_pe,jp_e)
                    jk,jl,l15,l20,shift,ket,status_final=hitung_final(masuk_dt,pulang_dt,st_e)
                    uang=get_uang_shift(id_edit, shift, float(jl))
                    rn=data_kar[data_kar['TANGGAL MASUK']==pilih_tgl].index[0]+2
                    ws_absen.update(f'A{rn}:N{rn}', [[id_edit, row['NAMA KARYAWAN'], tgl_e.strftime('%Y-%m-%d'), jm_e.strftime('%H:%M:%S'), tgl_pe.strftime('%Y-%m-%d'), jp_e.strftime('%H:%M:%S'), jk,jl,l15,l20,shift,ket,status_final,uang]])
                    load_data.clear(); st.success("Updated"); st.rerun()

with tab3:
    st.write("ADMIN - AUTO 23.59")
    if st.button("🚀 GENERATE LIBUR OTOMATIS SAMPAI HARI INI (FIX TGL 6 MINGGU)", use_container_width=True, type="primary"):
        vals=ws_absen.get_all_values()
        tgl_existing=[r[2] for r in vals[1:] if len(r)>2]
        today=date.today()
        count=0
        start_date = date(2026, 8, 1)
        d = start_date
        while d < today:
            d_str=d.strftime('%Y-%m-%d')
            if d_str not in tgl_existing:
                if d.weekday()==6:
                    row=["01213027","RACHMAT RAHARDJO",d_str,"",d_str,"","0.00","0.00","0.00","0.00","L","MINGGU","L","0"]
                    ws_absen.insert_row(row, 2); count+=1
                elif d_str in LIBUR_NASIONAL:
                    row=["01213027","RACHMAT RAHARDJO",d_str,"",d_str,"","0.00","0.00","0.00","0.00","SL",f"LIBUR NASIONAL {LIBUR_NASIONAL[d_str]}","L","0"]
                    ws_absen.insert_row(row, 2); count+=1
            d+=timedelta(days=1)
        load_data.clear()
        st.success(f"Berhasil generate {count} hari! Tgl 6 Minggu sekarang ada"); st.balloons(); st.rerun()

    if st.button("HAPUS DATA GAGAL 0.00 TGL 7", use_container_width=True):
        vals=ws_absen.get_all_values()
        for i,r in enumerate(vals[1:], start=2):
            if len(r)>=6 and r[2]=="2026-09-07" and r[5] in ["0.00","0",""]:
                ws_absen.delete_rows(i); break
        load_data.clear(); st.success("Hapus selesai"); st.rerun()

with tab4:
    st.write("REKAP - SUDAH AUTO 23.59")
    mode_r=st.radio("Mode", ["21-20 Payroll","Bulan Kalender","Custom"], horizontal=True, key="mode_r")
    c1,c2=st.columns(2)
    with c1: bulan_r=st.selectbox("Bulan", list(range(1,13)), index=datetime.now().month-1, key="bulan_r")
    with c2: tahun_r=st.number_input("Tahun", 2020, 2030, datetime.now().year, key="tahun_r")
    if mode_r=="Custom":
        cc1,cc2=st.columns(2)
        with cc1: awal_r=st.date_input("Dari", date(tahun_r,bulan_r,1), key="awal_r")
        with cc2: akhir_r=st.date_input("Sampai", date(tahun_r,bulan_r,calendar.monthrange(tahun_r,bulan_r)[1]), key="akhir_r")
    else: awal_r, akhir_r=get_periode(bulan_r,tahun_r,mode_r)
    st.success(f"{awal_r} s/d {akhir_r}")
    if not absen_df.empty:
        df_f=absen_df[(absen_df['TGL_DT']>=pd.to_datetime(awal_r))&(absen_df['TGL_DT']<=pd.to_datetime(akhir_r))]
        st.dataframe(df_f.sort_values('TGL_DT',ascending=False), use_container_width=True, height=500)

with tab5:
    st.write("GAJI")
    mode_g=st.radio("Mode Gaji", ["21-20 Payroll","Bulan Kalender"], horizontal=True, key="mode_g")
    c1,c2=st.columns(2)
    with c1: bulan_g=st.selectbox("Bulan Gaji", list(range(1,13)), index=datetime.now().month-1, key="bulan_g")
    with c2: tahun_g=st.number_input("Tahun Gaji", 2020, 2030, datetime.now().year, key="tahun_g")
    awal_g, akhir_g=get_periode(bulan_g,tahun_g,mode_g)
    st.info(f"Periode: {awal_g} s/d {akhir_g}")
    id_gaji=st.selectbox("Karyawan", db_df['ID KARYAWAN'].tolist() if not db_df.empty else ["01213027"])
    if st.button("HITUNG GAJI", type="primary", use_container_width=True):
        if not absen_df.empty:
            df_g=absen_df[(absen_df['ID KARYAWAN']==id_gaji)&(absen_df['TGL_DT']>=pd.to_datetime(awal_g))&(absen_df['TGL_DT']<=pd.to_datetime(akhir_g))]
            hadir=len(df_g[df_g['STATUS']=='H'])
            total_lembur=df_g['JAM LEMBUR'].astype(float).sum() if not df_g.empty else 0
            shift_malam=len(df_g[df_g['SHIFT'].astype(str).str.contains('S2|S3', na=False)])
            hari_lembur=len(df_g[df_g['JAM LEMBUR']>0]) if not df_g.empty else 0
            gaji_pokok=5252909; uang_makan=hadir*9500; uang_lembur=total_lembur*30000; uang_shift=shift_malam*2187; uang_makan_lembur=hari_lembur*9500
            total_pend=gaji_pokok+50000+uang_makan+uang_lembur+uang_shift+uang_makan_lembur+3500+12606+15758+194357+105058+210116
            total_pot=12606+15758+194357+105058+210116+105058+52529+52529
            total_gaji=total_pend-total_pot
            st.success(f"{len(df_g)} hari | Hadir {hadir} | Lembur {total_lembur}")
            c1,c2,c3=st.columns(3); c1.metric("Hadir", f"{hadir}"); c2.metric("Lembur", f"{total_lembur:.2f}"); c3.metric("TOTAL", f"Rp {int(total_gaji):,}")
