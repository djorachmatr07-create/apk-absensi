import streamlit as st, gspread, pandas as pd, requests, math, calendar
from datetime import datetime, timedelta, date, timezone
from google.oauth2.service_account import Credentials
from icalendar import Calendar
import streamlit.components.v1 as components

WIB = timezone(timedelta(hours=7))
st.set_page_config(page_title="SMART HR V38.3", layout="wide", page_icon="⚡")

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
        r=requests.get("https://calendar.google.com/calendar/ical/id.indonesian%23holiday%40group.v.calendar.google.com/public/basic.ics", timeout=10)
        cal=Calendar.from_ical(r.text); libur={}
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
    return db,absen,col_uang
db_df,absen_df,COL_UANG_SHIFT=load_data()

def is_missing(jam): return str(jam).strip() in ["","0","0.00","00:00:00","nan","None","NaT"]
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
    jam_float=total-1.0 if total>=6.0 else total if is_sabtu or status_input in ["GH","GHS"] else (total-1.0 if total>=6.0 else total)
    if jam_float<0: jam_float=0
    tgl_str=masuk_dt.strftime('%Y-%m-%d')
    status_final="H" if status_input in ["GH","GHS","H"] else status_input
    if status_input=="GH": return "7.00","0.00","0.00","0.00","H-S1","GANTI HARI",status_final
    if status_input=="GHS": return "5.00","0.00","0.00","0.00","H-S1","GANTI HARI SABTU",status_final
    jk,jl,l15,l20=hitung_lembur_bulat(jam_float, masuk_dt.weekday()==5, masuk_dt.weekday()==6, tgl_str in LIBUR_NASIONAL, status_input)
    ket="MINGGU" if masuk_dt.weekday()==6 else "SABTU" if masuk_dt.weekday()==5 else "MASUK"
    if tgl_str in LIBUR_NASIONAL: ket=f"LIBUR NASIONAL {LIBUR_NASIONAL[tgl_str]}"
    hm=masuk_dt.hour + masuk_dt.minute/60.0
    if 6 <= hm < 14: base='S1'
    elif 14 <= hm < 22: base='S2'
    else: base='S3'
    shift=status_final if status_final in ['A','L'] else f"H-{base}" if jam_float<11.5 else f"H-LS1" if base=='S1' else "H-LS2"
    return jk,jl,l15,l20,shift,ket,status_final

tab1,tab2,tab3=st.tabs(["ABSEN","ADMIN IZIN","REKAP"])

# === TAB ABSEN - FIX JAM MANUAL MUNCUL LAGI V38.2 ===
with tab1:
    id_in=st.text_input("ID ABSEN", value="01213027").strip().zfill(8)
    nama=db_df[db_df['ID KARYAWAN']==id_in]['NAMA KARYAWAN'].values[0] if id_in in db_df['ID KARYAWAN'].values else ""
    if nama: st.success(f"👋 {nama}")
    ubah_manual=st.checkbox("✏️ Ubah Tanggal & Jam Manual?", value=False)
    today_wib = now_wib().date()
    row_today=absen_df[(absen_df['ID KARYAWAN']==id_in)&(absen_df['TANGGAL MASUK']==today_wib.strftime('%Y-%m-%d'))&(~absen_df['JAM MASUK'].apply(lambda x: is_missing(x)))] if not absen_df.empty else pd.DataFrame()
    if row_today.empty:
        c1,c2=st.columns(2)
        if ubah_manual:
            tgl_m=c1.date_input("TANGGAL MASUK", value=date(2026,8,7), key="tgl_m")
            jam_m=c2.time_input("JAM MASUK", value=datetime.strptime("14:00:00", "%H:%M:%S").time(), key="jam_m")
        else:
            tgl_m=today_wib; jam_m=now_wib().time()
        if st.button("🟢 ABSEN MASUK", type="primary", use_container_width=True):
            if not ubah_manual:
                k=now_wib(); tgl_m=k.date(); jam_m=k.time()
            row=[id_in,nama,tgl_m.strftime('%Y-%m-%d'),datetime.combine(tgl_m, jam_m).strftime('%H:%M:%S'),"","","0.00","0.00","0.00","0.00","-","UNDEFINED","H","0"]
            ws_absen.insert_row(row,2); load_data.clear(); st.rerun()
    else:
        r=row_today.iloc[0]
        st.warning(f"✅ Masuk {r['TANGGAL MASUK']} {r['JAM MASUK']}")
        c1,c2=st.columns(2)
        if ubah_manual:
            tgl_p=c1.date_input("TANGGAL PULANG", value=today_wib, key="tgl_p")
            jam_p=c2.time_input("JAM PULANG", value=now_wib().time(), key="jam_p")
        else:
            tgl_p=today_wib; jam_p=now_wib().time()
        if st.button("🔴 PULANG SEKARANG", type="primary", use_container_width=True):
            if not ubah_manual:
                k=now_wib(); tgl_p=k.date(); jam_p=k.time()
            masuk_dt=datetime.combine(datetime.strptime(r['TANGGAL MASUK'], '%Y-%m-%d').date(), datetime.strptime(r['JAM MASUK'], '%H:%M:%S').time())
            pulang_dt=datetime.combine(tgl_p, jam_p)
            jk,jl,l15,l20,shift,ket,status_final=hitung_final(masuk_dt,pulang_dt,r['STATUS'])
            uang=get_uang_shift(id_in, shift, float(jl))
            rn=row_today.index[0]+2
            ws_absen.update(f'C{rn}:N{rn}', [[r['TANGGAL MASUK'],r['JAM MASUK'],tgl_p.strftime('%Y-%m-%d'),jam_p.strftime('%H:%M:%S'),jk,jl,l15,l20,shift,ket,status_final,uang]])
            load_data.clear(); st.rerun()

# === TAB ADMIN - V38.3 FIX TGL MUNCUL SETELAH NIK ===
with tab2:
    st.markdown("### 📝 MENU IZIN - V38.3 FIX")
    list_izin = [""] + db_df['ID KARYAWAN'].tolist()
    id_izin = st.selectbox("Pilih Karyawan", list_izin, key="id_izin", format_func=lambda x: "-- PILIH NIK DULU --" if x=="" else x)
    if id_izin!= "":
        nama_izin = db_df[db_df['ID KARYAWAN']==id_izin]['NAMA KARYAWAN'].values[0]
        st.info(f"👤 {id_izin} - {nama_izin}")
        c1,c2=st.columns(2)
        with c1: tgl_mulai_izin = st.date_input("Tanggal Mulai", value=now_wib().date(), key="tgl_mulai")
        with c2: tgl_selesai_izin = st.date_input("Tanggal Selesai", value=now_wib().date(), key="tgl_selesai")
        jenis_izin = st.selectbox("Jenis", ["SAKIT", "IZIN", "CUTI / IZIN CUTI", "DINAS LUAR", "KERJA DIRUMAH"], key="jenis")
        ket_izin = st.text_input("Keterangan", placeholder="mis: Cuti tahunan")
        mapping = {"SAKIT": ("S","SAKIT"), "IZIN": ("I","IZIN"), "CUTI / IZIN CUTI": ("L","CUTI"), "DINAS LUAR": ("DL","DINAS LUAR"), "KERJA DIRUMAH": ("WFH","KERJA DIRUMAH")}
        if st.button("💾 SIMPAN IZIN", type="primary", use_container_width=True):
            status_code, ket_default = mapping[jenis_izin]
            ket_final = ket_izin.upper() if ket_izin else ket_default
            delta = (tgl_selesai_izin - tgl_mulai_izin).days
            if delta < 0: st.error("Tanggal salah!")
            else:
                for d in range(delta+1):
                    tgl = tgl_mulai_izin + timedelta(days=d)
                    tgl_str = tgl.strftime('%Y-%m-%d')
                    cek = absen_df[(absen_df['ID KARYAWAN']==id_izin) & (absen_df['TANGGAL MASUK']==tgl_str)] if not absen_df.empty else pd.DataFrame()
                    if not cek.empty:
                        rn = cek.index[0]+2
                        ws_absen.update(f'C{rn}:N{rn}', [[tgl_str, "", tgl_str, "", "0.00","0.00","0.00","0.00","-",ket_final,status_code,"0"]])
                    else:
                        row_izin = [id_izin, nama_izin, tgl_str, "", tgl_str, "", "0.00","0.00","0.00","0.00","-",ket_final,status_code,"0"]
                        ws_absen.insert_row(row_izin, 2)
                load_data.clear(); st.success(f"✅ Izin {jenis_izin} {tgl_mulai_izin} s/d {tgl_selesai_izin} berhasil!"); st.balloons()
    else:
        st.warning("👆 Pilih NIK dulu min, nanti form Mulai, Selesai, Jenis muncul otomatis")
