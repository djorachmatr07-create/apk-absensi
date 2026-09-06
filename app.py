import streamlit as st, gspread, pandas as pd, requests, math, calendar
from datetime import datetime, timedelta, date, timezone
from google.oauth2.service_account import Credentials
from icalendar import Calendar
import streamlit.components.v1 as components

WIB = timezone(timedelta(hours=7))

st.set_page_config(page_title="NEXA PRO", layout="wide", page_icon="⚡")

st.markdown("""
<style>
  .main-title { font-size:30px; font-weight:900; letter-spacing:1px; margin-bottom:0px; }
  .sub-title { color:#6B7280; font-size:11px; margin-top:-6px; letter-spacing:2.5px; font-weight:600; }
</style>
<div class='main-title'>⚡ NEXA PRO</div>
<div class='sub-title'>SMART HR SYSTEM • AUTO WIB</div>
""", unsafe_allow_html=True)

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
        r=requests.get(ICS_URL, timeout=10); cal=Calendar.from_ical(r.text); libur={}
        for c in cal.walk():
            if c.name=="VEVENT":
                s=c.get('dtstart').dt
                if hasattr(s,'strftime'): s=s.strftime('%Y-%m-%d')
                libur[s]=str(c.get('summary'))
        return libur
    except: return {}
LIBUR_NASIONAL=get_libur()
HEADER=['ID KARYAWAN','NAMA KARYAWAN','TANGGAL MASUK','JAM MASUK','TANGGAL PULANG','JAM PULANG','JAM KERJA','JAM LEMBUR','LEMBUR 1.5','LEMBUR 2.0','SHIFT','KETERANGAN','STATUS','UANG SHIFT']

def now_wib(): return datetime.now(WIB)

@st.cache_data(ttl=60)
def load_data():
    db=pd.DataFrame(ws_db.get_all_records())
    db['ID KARYAWAN']=db['ID KARYAWAN'].astype(str).str.zfill(8)
    col_uang=[c for c in db.columns if 'SHIFT' in c.upper() and 'UANG' in c.upper()]
    col_uang=col_uang[0] if col_uang else db.columns[-1]
    vals=ws_absen.get_all_values()
    if len(vals)>1: absen=pd.DataFrame([r[:14] for r in vals[1:]], columns=HEADER)
    else: absen=pd.DataFrame(columns=HEADER)
    if not absen.empty:
        absen['ID KARYAWAN']=absen['ID KARYAWAN'].astype(str).str.zfill(8)
        absen['TGL_DT']=pd.to_datetime(absen['TANGGAL MASUK'],errors='coerce')
        absen['SHIFT']=absen['SHIFT'].fillna('').astype(str)
        absen['JAM LEMBUR']=pd.to_numeric(absen['JAM LEMBUR'],errors='coerce').fillna(0)
    return db,absen,col_uang
db_df,absen_df,COL_UANG_SHIFT=load_data()

def hitung_lembur_bulat(jam_float, is_sabtu=False, is_minggu=False, is_merah=False, status="H"):
    try: jam_float=float(jam_float or 0)
    except: jam_float=0.0
    jam_float=math.floor(jam_float+0.5)
    if jam_float<=0: return "0.00","0.00","0.00","0.00"
    if status in ["GH","GHS"]: return ("7.00","0.00","0.00","0.00") if status=="GH" else ("5.00","0.00","0.00","0.00")
    if is_sabtu:
        if jam_float<=5: return "5.00","0.00","0.00","0.00"
        sisa=jam_float-5; l15=1 if sisa>=1 else sisa; l20=sisa-1 if sisa>1 else 0; return "5.00",f"{l15*1.5+l20*2.0:.2f}",f"{l15:.2f}",f"{l20:.2f}"
    if is_minggu or is_merah: return "0.00",f"{jam_float*2.0:.2f}","0.00",f"{jam_float:.2f}"
    if jam_float<=7: return f"{jam_float:.2f}","0.00","0.00","0.00"
    sisa=jam_float-7; l15=1 if sisa>=1 else sisa; l20=sisa-1 if sisa>1 else 0; return "7.00",f"{l15*1.5+l20*2.0:.2f}",f"{l15:.2f}",f"{l20:.2f}"

def get_uang_shift(id_kar, shift, jl=0):
    try: v=str(db_df[db_df['ID KARYAWAN']==id_kar][COL_UANG_SHIFT].values[0]).replace('Rp','').replace('.','').replace(',','').strip()
    except: v="0"
    if v in ["","nan","None"]: v="0"
    if v=="0": return "0"
    if jl>0: return v
    if not any(x in str(shift).upper() for x in ['S2','S3','LS1','LS2']): return "0"
    return v

def hitung_final(masuk_dt,pulang_dt,status_input):
    if pulang_dt < masuk_dt: pulang_dt+=timedelta(days=1)
    total=(pulang_dt-masuk_dt).total_seconds()/3600
    is_sabtu=masuk_dt.weekday()==5
    jam_float=total-1.0 if total>6.0 else total if is_sabtu or status_input in ["GH","GHS"] else (total-1.0 if total>=6.0 else total)
    if jam_float<0: jam_float=0
    tgl_str=masuk_dt.strftime('%Y-%m-%d')
    status_final="H" if status_input in ["GH","GHS","H"] else status_input
    if status_input=="GH": return "7.00","0.00","0.00","0.00","H-S1","GANTI HARI",status_final
    if status_input=="GHS": return "5.00","0.00","0.00","0.00","H-S1","GANTI HARI SABTU",status_final
    jk,jl,l15,l20=hitung_lembur_bulat(jam_float, masuk_dt.weekday()==5, masuk_dt.weekday()==6, tgl_str in LIBUR_NASIONAL, status_input)
    ket="MINGGU" if masuk_dt.weekday()==6 else "SABTU" if masuk_dt.weekday()==5 else "MASUK"
    if tgl_str in LIBUR_NASIONAL: ket=f"LIBUR NASIONAL {LIBUR_NASIONAL[tgl_str]}"
    hm=masuk_dt.hour; base='S1' if 7<=hm<=14 else 'S2' if 15<=hm<=21 else 'S3'
    shift=status_final if status_final in ['A','L'] else f"H-{base}" if jam_float<11.5 else f"H-LS1" if base=='S1' else "H-LS2"
    return jk,jl,l15,l20,shift,ket,status_final

def get_periode(bulan,tahun,mode):
    if mode=="Bulan Kalender": return date(tahun,bulan,1), date(tahun,bulan,calendar.monthrange(tahun,bulan)[1])
    else:
        if bulan==1: return date(tahun-1,12,21), date(tahun,1,20)
        else: return date(tahun,bulan-1,21), date(tahun,bulan,20)

# GANTI GAJI JADI PAYROLL DISINI
tab1,tab2,tab3,tab4,tab5=st.tabs(["ABSEN","EDIT","ADMIN","REKAP","PAYROLL"])

with tab1:
    # JAM BERJALAN WIB - LIVE CLOCK
    components.html("""
    <div style="background:#111827; border-radius:12px; padding:14px 18px; border:1px solid #1F2937; text-align:center;">
        <div style="color:#9CA3AF; font-size:11px; letter-spacing:3px; font-weight:700;">WAKTU REALTIME WIB</div>
        <div id="clock" style="color:#22C55E; font-size:36px; font-weight:900; font-family:monospace; letter-spacing:2px;">--:--:--</div>
        <div id="date" style="color:#E5E7EB; font-size:13px; margin-top:2px;"></div>
    </div>
    <script>
    function updateClock(){
        const now = new Date();
        const wib = new Date(now.toLocaleString('en-US', {timeZone: 'Asia/Jakarta'}));
        const jam = String(wib.getHours()).padStart(2,'0');
        const menit = String(wib.getMinutes()).padStart(2,'0');
        const detik = String(wib.getSeconds()).padStart(2,'0');
        const tgl = wib.toLocaleDateString('id-ID', {weekday:'long', day:'2-digit', month:'long', year:'numeric'});
        document.getElementById('clock').innerText = jam+':'+menit+':'+detik+' WIB';
        document.getElementById('date').innerText = tgl;
    }
    setInterval(updateClock, 1000);
    updateClock();
    </script>
    """, height=110)

    id_in=st.text_input("ID ABSEN", value="01213027").strip().zfill(8)
    nama=db_df[db_df['ID KARYAWAN']==id_in]['NAMA KARYAWAN'].values[0] if id_in in db_df['ID KARYAWAN'].values else ""
    if nama: st.success(f"👋 {nama}")
    ubah_manual=st.checkbox("✏️ Ubah Tanggal & Jam Manual?")
    today_wib = now_wib().date()
    today_str = today_wib.strftime('%Y-%m-%d')
    now_time_wib = now_wib().time()
    row_today=absen_df[(absen_df['ID KARYAWAN']==id_in)&(absen_df['TANGGAL MASUK']==today_str)&(absen_df['JAM MASUK']!="")] if not absen_df.empty else pd.DataFrame()

    if row_today.empty:
        st.info(f"📅 {today_str} WIB • Siap Absen")
        status_pilih=st.selectbox("Status", ["H","GH","GHS","I","S","A"], key="st_masuk")
        c1,c2=st.columns(2)
        if ubah_manual:
            tgl_m=c1.date_input("TANGGAL MASUK", value=today_wib, key="tgl_m")
            jam_m=c2.time_input("JAM MASUK", value=now_time_wib, key="jam_m")
        else:
            tgl_m=today_wib; jam_m=now_time_wib
            c1.metric("TGL MASUK", str(tgl_m)); c2.metric("JAM MASUK", jam_m.strftime('%H:%M:%S'))
        if st.button("🟢 ABSEN MASUK", type="primary", use_container_width=True):
            vals=ws_absen.get_all_values()
            for i,r in enumerate(vals[1:], start=2):
                if len(r)>2 and r[0]==id_in and r[2]==tgl_m.strftime('%Y-%m-%d') and r[3]=="":
                    ws_absen.delete_rows(i); break
            masuk_dt=datetime.combine(tgl_m, jam_m)
            row=[id_in,nama,tgl_m.strftime('%Y-%m-%d'),masuk_dt.strftime('%H:%M:%S'),"","","0.00","0.00","0.00","0.00","-","MASUK","H","0"]
            ws_absen.insert_row(row,2); load_data.clear(); st.success(f"MASUK {tgl_m} OK"); st.balloons(); st.rerun()
    else:
        r=row_today.iloc[0]
        if r['JAM PULANG']=="" or r['JAM PULANG'] in ["0.00","0"]:
            st.warning(f"✅ Masuk {r['TANGGAL MASUK']} {r['JAM MASUK']} - Belum Pulang")
            c1,c2=st.columns(2)
            if ubah_manual:
                tgl_p=c1.date_input("TANGGAL PULANG", value=today_wib, key="tgl_p")
                jam_p=c2.time_input("JAM PULANG", value=now_time_wib, key="jam_p")
            else:
                tgl_p=today_wib; jam_p=now_time_wib
                try:
                    if jam_p < datetime.strptime(r['JAM MASUK'], '%H:%M:%S').time(): tgl_p=today_wib+timedelta(days=1)
                except: pass
                c1.metric("TGL PULANG", str(tgl_p)); c2.metric("JAM PULANG", jam_p.strftime('%H:%M:%S'))
            if st.button("🔴 ABSEN PULANG SEKARANG", type="primary", use_container_width=True):
                masuk_dt=datetime.combine(datetime.strptime(r['TANGGAL MASUK'], '%Y-%m-%d').date(), datetime.strptime(r['JAM MASUK'], '%H:%M:%S').time())
                pulang_dt=datetime.combine(tgl_p, jam_p)
                jk,jl,l15,l20,shift,ket,status_final=hitung_final(masuk_dt,pulang_dt,r['STATUS'])
                uang=get_uang_shift(id_in, shift, float(jl))
                rn=row_today.index[0]+2
                ws_absen.update(f'C{rn}:N{rn}', [[r['TANGGAL MASUK'],r['JAM MASUK'],tgl_p.strftime('%Y-%m-%d'),jam_p.strftime('%H:%M:%S'),jk,jl,l15,l20,shift,ket,status_final,uang]])
                load_data.clear(); st.success(f"PULANG {jk} jam"); st.balloons(); st.rerun()
        else:
            st.success(f"✅ {r['TANGGAL MASUK']} {r['JAM MASUK']} → {r['TANGGAL PULANG']} {r['JAM PULANG']} | {r['SHIFT']}")

with tab2:
    st.markdown("#### EDIT DATA")
    if "login" not in st.session_state: st.session_state.login=False
    if not st.session_state.login:
        pw=st.text_input("Password ADMIN", type="password")
        if st.button("LOGIN"):
            if pw==PASSWORD_ADMIN: st.session_state.login=True; st.rerun()
    else:
        if st.button("LOGOUT"): st.session_state.login=False; st.rerun()
        id_edit=st.text_input("ID EDIT", value="01213027").strip().zfill(8)
        if id_edit in db_df['ID KARYAWAN'].values:
            data_kar=absen_df[absen_df['ID KARYAWAN']==id_edit].sort_values('TGL_DT', ascending=False)
            if not data_kar.empty:
                pilih_tgl=st.selectbox("Pilih Tanggal", data_kar['TANGGAL MASUK'].tolist())
                row=data_kar[data_kar['TANGGAL MASUK']==pilih_tgl].iloc[0]
                st.info(f"{row['TANGGAL MASUK']} {row['JAM MASUK']} → {row['JAM PULANG']} | {row['SHIFT']}")
                c1,c2=st.columns(2)
                with c1:
                    tgl_e=st.date_input("Tgl Masuk", pd.to_datetime(row['TANGGAL MASUK']).date())
                    jm_e=st.time_input("Jam Masuk", datetime.strptime(row['JAM MASUK'], '%H:%M:%S').time() if row['JAM MASUK'] and row['JAM MASUK'] not in ["0.00",""] else now_wib().time())
                with c2:
                    tgl_pe=st.date_input("Tgl Pulang", pd.to_datetime(row['TANGGAL PULANG']).date() if row['TANGGAL PULANG'] and row['TANGGAL PULANG'] not in ["","0.00"] else pd.to_datetime(row['TANGGAL MASUK']).date())
                    jp_e=st.time_input("Jam Pulang", datetime.strptime(row['JAM PULANG'], '%H:%M:%S').time() if row['JAM PULANG'] and row['JAM PULANG'] not in ["","0.00"] else now_wib().time())
                st_e=st.selectbox("Status", ["H","GH","GHS","A","L","I","S","TL"])
                if st.button("UPDATE", type="primary", use_container_width=True):
                    masuk_dt=datetime.combine(tgl_e, jm_e); pulang_dt=datetime.combine(tgl_pe, jp_e)
                    jk,jl,l15,l20,shift,ket,status_final=hitung_final(masuk_dt,pulang_dt,st_e)
                    uang=get_uang_shift(id_edit, shift, float(jl))
                    rn=data_kar[data_kar['TANGGAL MASUK']==pilih_tgl].index[0]+2
                    ws_absen.update(f'A{rn}:N{rn}', [[id_edit, row['NAMA KARYAWAN'], tgl_e.strftime('%Y-%m-%d'), jm_e.strftime('%H:%M:%S'), tgl_pe.strftime('%Y-%m-%d'), jp_e.strftime('%H:%M:%S'), jk,jl,l15,l20,shift,ket,status_final,uang]])
                    load_data.clear(); st.success("Updated"); st.rerun()

with tab3:
    st.markdown("#### ADMIN")
    if st.button("🚀 GENERATE ALL", type="primary", use_container_width=True):
        vals=ws_absen.get_all_values()
        to_del=[]
        for i,r in enumerate(vals[1:], start=2):
            if len(r)>=3 and r[2] in ["2026-08-04","2026-08-06","2026-08-07","2026-08-08","2026-08-09","2026-08-10","2026-08-11","2026-08-12","2026-08-13","2026-08-14"] and (len(r)>11 and r[11]=="TIDAK MASUK"):
                to_del.append(i)
        for idx in sorted(to_del, reverse=True): ws_absen.delete_rows(idx)
        vals=ws_absen.get_all_values(); existing=[r[2] for r in vals[1:] if len(r)>2]
        start_d=date(2026,9,6); end_d=now_wib().date(); cnt=0; d=start_d
        while d < end_d:
            ds=d.strftime('%Y-%m-%d')
            if ds not in existing:
                if d.weekday()==6:
                    ws_absen.insert_row(["01213027","RACHMAT RAHARDJO",ds,"",ds,"","0.00","0.00","L","MINGGU","L","0"],2); cnt+=1
                elif ds in LIBUR_NASIONAL:
                    ws_absen.insert_row(["01213027","RACHMAT RAHARDJO",ds,"",ds,"","0.00","0.00","SL",f"LIBUR NASIONAL {LIBUR_NASIONAL[ds]}","L","0"],2); cnt+=1
            d+=timedelta(days=1)
        load_data.clear(); st.success(f"Fix {len(to_del)} + Generate {cnt}"); st.balloons(); st.rerun()

with tab4:
    st.markdown("#### REKAP")
    mode_r=st.radio("Mode", ["21-20 Payroll","Bulan Kalender","Custom"], horizontal=True)
    c1,c2=st.columns(2)
    with c1: bulan_r=st.selectbox("Bulan", list(range(1,13)), index=now_wib().month-1)
    with c2: tahun_r=st.number_input("Tahun", 2020, 2030, now_wib().year)
    if mode_r=="Custom":
        cc1,cc2=st.columns(2)
        with cc1: awal_r=st.date_input("Dari", date(tahun_r,bulan_r,1))
        with cc2: akhir_r=st.date_input("Sampai", date(tahun_r,bulan_r,calendar.monthrange(tahun_r,bulan_r)[1]))
    else: awal_r,akhir_r=get_periode(bulan_r,tahun_r,mode_r)
    st.success(f"{awal_r} → {akhir_r}")
    if not absen_df.empty:
        df_f=absen_df[(absen_df['TGL_DT']>=pd.to_datetime(awal_r))&(absen_df['TGL_DT']<=pd.to_datetime(akhir_r))]
        st.dataframe(df_f.sort_values('TGL_DT',ascending=False), use_container_width=True, height=600)

with tab5:
    st.markdown("#### PAYROLL • GAJI")
    mode_g=st.radio("Mode Gaji", ["21-20 Payroll","Bulan Kalender"], horizontal=True, key="mode_g")
    c1,c2=st.columns(2)
    with c1: bulan_g=st.selectbox("Bulan Gaji", list(range(1,13)), index=now_wib().month-1, key="bulan_g")
    with c2: tahun_g=st.number_input("Tahun Gaji", 2020, 2030, now_wib().year, key="tahun_g")
    awal_g,akhir_g=get_periode(bulan_g,tahun_g,mode_g)
    st.info(f"Periode: {awal_g} s/d {akhir_g}")
    id_gaji=st.selectbox("Karyawan", db_df['ID KARYAWAN'].tolist())
    if st.button("HITUNG PAYROLL", type="primary", use_container_width=True):
        df_g=absen_df[(absen_df['ID KARYAWAN']==id_gaji)&(absen_df['TGL_DT']>=pd.to_datetime(awal_g))&(absen_df['TGL_DT']<=pd.to_datetime(akhir_g))].copy()
        if df_g.empty: st.warning("Data kosong")
        else:
            df_g['SHIFT']=df_g['SHIFT'].fillna('').astype(str)
            hadir=len(df_g[df_g['STATUS']=='H'])
            total_lembur=pd.to_numeric(df_g['JAM LEMBUR'],errors='coerce').fillna(0).sum()
            shift_malam=len(df_g[df_g['SHIFT'].str.contains('S2|S3|LS1|LS2', na=False)])
            hari_lembur=len(df_g[pd.to_numeric(df_g['JAM LEMBUR'],errors='coerce').fillna(0)>0])
            gaji_pokok=5252909; uang_makan=hadir*9500; uang_lembur=total_lembur*30000; uang_shift=shift_malam*2187; uang_makan_lembur=hari_lembur*9500
            total_pend=gaji_pokok+50000+uang_makan+uang_lembur+uang_shift+uang_makan_lembur+3500+12606+15758+194357+105058+210116
            total_pot=12606+15758+194357+105058+210116+105058+52529+52529
            total_gaji=total_pend-total_pot
            st.dataframe(df_g, use_container_width=True)
            c1,c2,c3=st.columns(3); c1.metric("Hadir", hadir); c2.metric("Lembur", f"{total_lembur:.2f}"); c3.metric("TOTAL PAYROLL", f"Rp {int(total_gaji):,}")
            try:
                ws_gaji.batch_update([{'range':'B5','values':[[f"{hadir} Hari x 9500"]]},{'range':'C5','values':[[int(uang_makan)]]},{'range':'B7','values':[[f"{total_lembur:.2f} Jam x 30000"]]},{'range':'C7','values':[[int(uang_lembur)]]},{'range':'B8','values':[[f"{shift_malam} Hari x 2187"]]},{'range':'C8','values':[[int(uang_shift)]]},{'range':'B9','values':[[f"{hari_lembur} Hari x 9500"]]},{'range':'C9','values':[[int(uang_makan_lembur)]]},{'range':'C17','values':[[int(total_pend)]]},{'range':'E17','values':[[int(total_pot)]]},{'range':'C19','values':[[int(total_gaji)]]}])
                st.success(f"✅ PAYROLL Rp {int(total_gaji):,} Updated"); st.balloons()
            except Exception as e: st.error(f"Error: {e}")
