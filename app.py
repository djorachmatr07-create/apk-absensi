import streamlit as st, gspread, pandas as pd, requests, math, calendar
from datetime import datetime, timedelta, date
from google.oauth2.service_account import Credentials
from icalendar import Calendar

st.set_page_config(page_title="NEXA V16 SIMPLE", layout="wide", page_icon="🛰️")
st.markdown("<h2>🛰️ NEXA V16 SIMPLE</h2><p style='color:#9CA3AF;font-size:12px'>TANGGAL MASUK | TANGGAL PULANG | 1 HARI 2 KLIK</p>", unsafe_allow_html=True)

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

# 5 MENU
tab1, tab2, tab3, tab4, tab5 = st.tabs(["ABSEN","EDIT","ADMIN","REKAP","GAJI"])

with tab1:
    st.markdown("### ABSEN SIMPLE - 2 KLIK")
    id_in=st.text_input("ID ABSEN", value="01213027").strip().zfill(8)
    nama=""
    if id_in and id_in in db_df['ID KARYAWAN'].values:
        nama=db_df[db_df['ID KARYAWAN']==id_in]['NAMA KARYAWAN'].values[0]
        st.success(f"👋 {nama}")

    if not nama:
        st.warning("Isi ID dulu min")
    else:
        # CEK STATUS HARI INI
        today_str = datetime.now().strftime('%Y-%m-%d')
        # cari absen hari ini
        row_today = absen_df[(absen_df['ID KARYAWAN']==id_in)&(absen_df['TANGGAL MASUK']==today_str)] if not absen_df.empty else pd.DataFrame()

        if row_today.empty:
            # BELUM ABSEN - CUMA MUNCUL ABSEN MASUK
            st.info(f"📅 Hari ini {today_str} belum absen")
            status_pilih=st.selectbox("Status", ["H","GH","GHS","I","S","A"], key="st_masuk")
            jam_masuk_now = datetime.now().time()
            st.metric("Jam Sekarang", jam_masuk_now.strftime('%H:%M:%S'))
            if st.button("🟢 ABSEN MASUK SEKARANG", type="primary", use_container_width=True):
                masuk_dt = datetime.combine(date.today(), jam_masuk_now)
                # simpan dulu dengan pulang kosong - nanti diisi pas pulang
                row = [id_in, nama, today_str, masuk_dt.strftime('%H:%M:%S'), "", "0.00","0.00","0.00","0.00", "-", "MASUK", status_pilih if status_pilih!="H" else "H", "0"]
                # kalau GH/GHS
                if status_pilih=="GH": row[6]="7.00"; row[11]="GANTI HARI"
                if status_pilih=="GHS": row[6]="5.00"; row[11]="GANTI HARI SABTU"
                ws_absen.insert_row(row,2)
                load_data.clear()
                st.success(f"Absen MASUK {today_str} {row[3]} berhasil!"); st.balloons(); st.rerun()
        else:
            r = row_today.iloc[0]
            jam_masuk_sudah = r['JAM MASUK']
            jam_pulang_sudah = r['JAM PULANG']
            if jam_pulang_sudah=="" or jam_pulang_sudah=="0" or pd.isna(jam_pulang_sudah):
                # SUDAH MASUK, BELUM PULANG - CUMA MUNCUL ABSEN PULANG
                st.warning(f"✅ Sudah masuk jam {jam_masuk_sudah} - belum pulang")
                jam_pulang_now = datetime.now().time()
                # auto tanggal pulang - kalau masuk 22:00 dan sekarang 07:00, tanggal pulang besok
                tgl_pulang_auto = date.today()
                try:
                    masuk_t = datetime.strptime(jam_masuk_sudah, '%H:%M:%S').time()
                    if jam_pulang_now < masuk_t: tgl_pulang_auto = date.today() + timedelta(days=1)
                except: pass
                st.metric("Tanggal Pulang Auto", str(tgl_pulang_auto))
                st.metric("Jam Pulang Sekarang", jam_pulang_now.strftime('%H:%M:%S'))
                if st.button("🔴 ABSEN PULANG SEKARANG", type="primary", use_container_width=True):
                    try:
                        masuk_dt = datetime.combine(datetime.strptime(r['TANGGAL MASUK'], '%Y-%m-%d').date(), datetime.strptime(jam_masuk_sudah, '%H:%M:%S').time())
                    except:
                        masuk_dt = datetime.combine(date.today(), datetime.strptime(jam_masuk_sudah, '%H:%M:%S').time())
                    pulang_dt = datetime.combine(tgl_pulang_auto, jam_pulang_now)
                    jk,jl,l15,l20,shift,ket,status_final = hitung_final(masuk_dt, pulang_dt, r['STATUS'])
                    try: jl_f=float(jl)
                    except: jl_f=0
                    uang=get_uang_shift(id_in, shift, jl_f)
                    rn = row_today.index[0]+2
                    ws_absen.update(f'C{rn}:N{rn}', [[r['TANGGAL MASUK'], jam_masuk_sudah, tgl_pulang_auto.strftime('%Y-%m-%d'), jam_pulang_now.strftime('%H:%M:%S'), jk,jl,l15,l20,shift,ket,status_final,uang]])
                    load_data.clear()
                    st.success(f"Absen PULANG {tgl_pulang_auto} {jam_pulang_now.strftime('%H:%M:%S')} - Kerja {jk} jam, Lembur {jl} jam"); st.balloons(); st.rerun()
            else:
                # SUDAH LENGKAP
                st.success(f"✅ HARI INI SELESAI: Masuk {r['TANGGAL MASUK']} {r['JAM MASUK']} -> Pulang {r['TANGGAL PULANG']} {r['JAM PULANG']} | {r['SHIFT']} {r['JAM KERJA']} jam")
                st.balloons()
                if st.button("Lihat REKAP", use_container_width=True): st.switch_page

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
                pilih_tgl=st.selectbox("Tanggal Masuk", data_kar.sort_values('TGL_DT',ascending=False)['TANGGAL MASUK'].tolist())
                row=data_kar[data_kar['TANGGAL MASUK']==pilih_tgl].iloc[0]
                st.write(f"{row['TANGGAL MASUK']} {row['JAM MASUK']} -> {row['TANGGAL PULANG']} {row['JAM PULANG']} {row['SHIFT']}")
                c1,c2=st.columns(2)
                with c1: tgl_e=st.date_input("Tgl Masuk Edit", pd.to_datetime(row['TANGGAL MASUK'])); jm_e=st.time_input("Masuk Edit", datetime.strptime(row['JAM MASUK'],'%H:%M:%S').time() if row['JAM MASUK'] else datetime.now().time())
                with c2: tgl_pe=st.date_input("Tgl Pulang Edit", pd.to_datetime(row['TANGGAL PULANG']) if row['TANGGAL PULANG'] else pd.to_datetime(row['TANGGAL MASUK'])); jp_e=st.time_input("Pulang Edit", datetime.strptime(row['JAM PULANG'],'%H:%M:%S').time() if row['JAM PULANG'] else datetime.now().time())
                st_e=st.selectbox("Status Baru", ["H","GH","GHS","TL","I","S","C","A","L"])
                if st.button("UPDATE",type="primary",use_container_width=True):
                    masuk_dt=datetime.combine(tgl_e,jm_e); pulang_dt=datetime.combine(tgl_pe,jp_e)
                    jk,jl,l15,l20,shift,ket,status_final=hitung_final(masuk_dt,pulang_dt,st_e)
                    try: jl_f=float(jl)
                    except: jl_f=0
                    uang=get_uang_shift(id_edit, shift, jl_f)
                    rn=data_kar[data_kar['TANGGAL MASUK']==pilih_tgl].index[0]+2
                    ws_absen.update(f'A{rn}:N{rn}', [[id_edit, row['NAMA KARYAWAN'], tgl_e.strftime('%Y-%m-%d'), jm_e.strftime('%H:%M:%S'), tgl_pe.strftime('%Y-%m-%d'), jp_e.strftime('%H:%M:%S'), jk,jl,l15,l20,shift,ket,status_final,uang]])
                    load_data.clear(); st.success("Updated"); st.rerun()

with tab3:
    st.write("ADMIN")
    if st.button("MIGRASI TANGGAL PULANG - ISI YANG KOSONG", use_container_width=True):
        vals=ws_absen.get_all_values()
        for i,r in enumerate(vals[1:], start=2):
            if len(r)<6: continue
            try:
                if r[4]=="":
                    tgl_m=datetime.strptime(r[2], '%Y-%m-%d'); jm=datetime.strptime(r[3], '%H:%M:%S'); jp=datetime.strptime(r[5], '%H:%M:%S') if r[5] else jm
                    pulang=datetime.combine(tgl_m.date(), jp.time()); masuk=datetime.combine(tgl_m.date(), jm.time())
                    if pulang < masuk: pulang+=timedelta(days=1)
                    ws_absen.update(f'E{i}', [[pulang.strftime('%Y-%m-%d')]])
            except: pass
        st.success("Migrasi selesai"); load_data.clear(); st.rerun()

with tab4:
    st.write("REKAP PERIODE")
    mode_r=st.radio("Mode Rekap", ["21-20 Payroll","Bulan Kalender","Custom"], horizontal=True, key="mode_r")
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
        st.dataframe(df_f, use_container_width=True, height=500)

with tab5:
    st.write("GAJI PERIODE - 5.7JT")
    mode_g=st.radio("Mode Gaji", ["21-20 Payroll","Bulan Kalender"], horizontal=True, key="mode_g")
    c1,c2=st.columns(2)
    with c1: bulan_g=st.selectbox("Bulan Gaji", list(range(1,13)), index=datetime.now().month-1, key="bulan_g")
    with c2: tahun_g=st.number_input("Tahun Gaji", 2020, 2030, datetime.now().year, key="tahun_g")
    if mode_g=="Custom":
        cc1,cc2=st.columns(2)
        with cc1: awal_g=st.date_input("Dari Tgl Gaji", date(tahun_g,bulan_g,1), key="awal_g")
        with cc2: akhir_g=st.date_input("Sampai Tgl Gaji", date(tahun_g,bulan_g,calendar.monthrange(tahun_g,bulan_g)[1]), key="akhir_g")
    else: awal_g, akhir_g=get_periode(bulan_g,tahun_g,mode_g)
    st.info(f"Periode Gaji: {awal_g} s/d {akhir_g}")
    id_gaji=st.selectbox("Karyawan", db_df['ID KARYAWAN'].tolist() if not db_df.empty else ["01213027"])
    if st.button("HITUNG REAL + UPDATE SHEET GAJI", type="primary", use_container_width=True):
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
            st.dataframe(df_g, use_container_width=True)
            c1,c2,c3=st.columns(3); c1.metric("Hadir", f"{hadir} Hari"); c2.metric("Lembur", f"{total_lembur:.2f}"); c3.metric("TOTAL GAJI", f"Rp {int(total_gaji):,}")
            ws_gaji.batch_update([
                {'range': 'B5', 'values': [[f"{hadir} Hari x 9500"]]},{'range': 'C5', 'values': [[int(uang_makan)]]},
                {'range': 'B7', 'values': [[f"{total_lembur:.2f} Jam x 30000"]]},{'range': 'C7', 'values': [[int(uang_lembur)]]},
                {'range': 'B8', 'values': [[f"{shift_malam} Hari x 2187"]]},{'range': 'C8', 'values': [[int(uang_shift)]]},
                {'range': 'B9', 'values': [[f"{hari_lembur} Hari x 9500"]]},{'range': 'C9', 'values': [[int(uang_makan_lembur)]]},
                {'range': 'C17', 'values': [[int(total_pend)]]},{'range': 'E17', 'values': [[int(total_pot)]]},{'range': 'C19', 'values': [[int(total_gaji)]]},
            ])
            st.success(f"✅ Updated Rp {int(total_gaji):,}"); st.balloons()
