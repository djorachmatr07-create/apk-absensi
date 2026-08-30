import streamlit as st, gspread, pandas as pd, requests, math
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from icalendar import Calendar

st.set_page_config(page_title="V10.8.5 BULAT GH GHS", layout="wide")
st.title("📍 V10.8.5 - BULAT NO KOMA + GH & GHS")

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

# ================= RUMUS BULAT + GH GHS =================
def hitung_lembur_bulat(jam_total_float, is_sabtu=False, is_minggu=False, is_merah=False, status="H"):
    try: jam_total_float=float(jam_total_float or 0)
    except: jam_total_float=0.0

    # BULATKAN DULU KAYAK JAM KERJA - NO KOMA
    jam_total_float = math.floor(jam_total_float + 0.5) # 7.27 jadi 7, 2.13 jadi 2, 2.6 jadi 3

    if jam_total_float <=0:
        return "0.00","0.00","0.00","0.00"

    # GH = GANTI HARI (dianggap hari kerja biasa 7 jam)
    if status == "GH":
        if jam_total_float <=7: return f"{jam_total_float:.2f}","0.00","0.00","0.00"
        sisa=jam_total_float-7
        l15=1 if sisa>=1 else sisa
        l20=sisa-1 if sisa>1 else 0
        return "7.00",f"{sisa:.2f}",f"{l15:.2f}",f"{l20:.2f}"

    # GHS = GANTI HARI SABTU (dianggap Sabtu 5 jam)
    if status == "GHS":
        if jam_total_float <=5: return f"{jam_total_float:.2f}","0.00","0.00","0.00"
        sisa=jam_total_float-5
        l15=1 if sisa>=1 else sisa
        l20=sisa-1 if sisa>1 else 0
        return "5.00",f"{sisa:.2f}",f"{l15:.2f}",f"{l20:.2f}"

    # MINGGU & MERAH: 7 JAM X2.0 BULAT
    if is_minggu or is_merah:
        return "0.00",f"{jam_total_float:.2f}","0.00",f"{jam_total_float:.2f}"

    # SABTU: 5 JAM + 1x1.5 + SISANYA x2.0 BULAT
    if is_sabtu:
        if jam_total_float <=5:
            return f"{jam_total_float:.2f}","0.00","0.00","0.00"
        sisa=jam_total_float-5
        l15=1 if sisa>=1 else sisa
        l20=sisa-1 if sisa>1 else 0
        return "5.00",f"{sisa:.2f}",f"{l15:.2f}",f"{l20:.2f}"

    # SENIN-JUMAT
    if jam_total_float <=7:
        return f"{jam_total_float:.2f}","0.00","0.00","0.00"
    sisa=jam_total_float-7
    l15=1 if sisa>=1 else sisa
    l20=sisa-1 if sisa>1 else 0
    return "7.00",f"{sisa:.2f}",f"{l15:.2f}",f"{l20:.2f}"

@st.cache_data(ttl=60)
def load_data():
    db=pd.DataFrame(ws_db.get_all_records())
    db['ID KARYAWAN']=db['ID KARYAWAN'].astype(str).str.zfill(8)
    col_uang=None
    for c in db.columns:
        if 'SHIFT' in c.upper() and 'UANG' in c.upper(): col_uang=c
    if not col_uang: col_uang=db.columns[-1]
    all_values=ws_absen.get_all_values()
    if len(all_values)>1:
        data=[row[:13] for row in all_values[1:]]
        absen=pd.DataFrame(data,columns=HEADER) if data else pd.DataFrame(columns=HEADER)
    else: absen=pd.DataFrame(columns=HEADER)
    if not absen.empty:
        absen['ID KARYAWAN']=absen['ID KARYAWAN'].astype(str).str.zfill(8)
        absen['TGL_DT']=pd.to_datetime(absen['TANGGAL'],format='%Y-%m-%d',errors='coerce')
    return db,absen,col_uang
db_df,absen_df,COL_UANG_SHIFT=load_data()

def get_uang_shift(id_kar, shift_code):
    if not shift_code: return "0"
    shift_code=str(shift_code).upper()
    if not any(x in shift_code for x in ['S2','S3','LS1','LS2']): return "0"
    try:
        val=db_df[db_df['ID KARYAWAN']==id_kar][COL_UANG_SHIFT].values[0]
        val=str(val).replace('Rp','').replace('.','').replace(',','').strip()
        return "0" if val=='' or val.lower()=='nan' else val
    except: return "0"

def bulatkan_ke_jam_pas(dt): return dt.replace(second=0,microsecond=0)

def cek_keterangan(tgl_dt,jam_masuk_str="",jam_pulang_str="",jam_float=0,status="H"):
    tgl_str=tgl_dt.strftime('%Y-%m-%d')
    wd=tgl_dt.weekday()
    if tgl_str in LIBUR_NASIONAL:
        if status in ["GH","GHS"]: return f"GANTI HARI - {LIBUR_NASIONAL[tgl_str]}"
        return f"LIBUR NASIONAL: {LIBUR_NASIONAL[tgl_str]}"
    if jam_masuk_str and jam_pulang_str and jam_float>0:
        if status=="GH": return "GANTI HARI"
        if status=="GHS": return "GANTI HARI SABTU"
        return "MASUK"
    if jam_float==0:
        if status=='L': return "SHIFT LIBUR"
        if status=='A': return "ALFA"
        if status=='I': return "IZIN"
        if status=='S': return "SAKIT"
        if status=='C': return "CUTI"
        if status=='TL': return "TUKAR LIBUR"
        if status=='GH': return "GANTI HARI"
        if status=='GHS': return "GANTI HARI SABTU"
        if wd==6: return "LIBUR MINGGU"
        if wd==5: return "SABTU"
        return "TIDAK MASUK"
    return "HARI KERJA"

def cek_shift(jam_masuk_dt,jam_kerja_float,keterangan,status):
    if 'LIBUR' in keterangan and status not in ["GH","GHS"]: return 'SL'
    if status in ['A','I','S','C','TL']: return status
    if status in ['GH','GHS']: return status
    if jam_kerja_float==0: return '-'
    hm=jam_masuk_dt.hour
    if hm>=19: return f"{status}-LS2"
    if jam_kerja_float>=11.5: sc='LS1'
    else:
        if 7<=hm<15: sc='S1'
        elif 15<=hm<23: sc='S2'
        else: sc='S3'
    return f"{status}-{sc}" if keterangan=="MASUK" or "GANTI" in keterangan else sc

def hitung(masuk_dt,pulang_dt,status):
    masuk_dt=bulatkan_ke_jam_pas(masuk_dt)
    pulang_dt=bulatkan_ke_jam_pas(pulang_dt)
    if pulang_dt<masuk_dt: pulang_dt+=timedelta(days=1)
    total=(pulang_dt-masuk_dt).total_seconds()/3600
    jam_float=total-1.0 if total>=6.0 else total
    if jam_float<0: jam_float=0
    tgl_str=masuk_dt.strftime('%Y-%m-%d')
    is_sabtu=masuk_dt.weekday()==5
    is_minggu=masuk_dt.weekday()==6
    is_merah=tgl_str in LIBUR_NASIONAL
    jm_str=masuk_dt.strftime('%H:%M:%S')
    jp_str=pulang_dt.strftime('%H:%M:%S')
    ket=cek_keterangan(masuk_dt,jm_str,jp_str,jam_float,status)
    shift=cek_shift(masuk_dt,jam_float,ket,status)
    jk,jl,l15,l20=hitung_lembur_bulat(jam_float,is_sabtu,is_minggu,is_merah,status)
    return jk,jl,l15,l20,shift,ket,jm_str,jp_str

def upsert_absen(id_kar,masuk_dt,pulang_dt,nama,status="H",sudah_pulang=False):
    id_kar=id_kar.zfill(8)
    tgl_str=masuk_dt.strftime('%Y-%m-%d')
    if status in ['A','I','S','C','L','TL'] and status not in ["GH","GHS"]:
        jm="";jp="";jk="0.00";jl="0.00";l1="0.00";l2="0.00"
        shift='SL' if tgl_str in LIBUR_NASIONAL else status
        ket=cek_keterangan(masuk_dt,"","",0,status)
    elif not sudah_pulang:
        jm=masuk_dt.strftime('%H:%M:%S');jp="";jk="0.00";jl="0.00";l1="0.00";l2="0.00"
        shift="-";ket="BELUM ABSEN PULANG"
    else:
        jk,jl,l1,l2,shift,ket,jm,jp=hitung(masuk_dt,pulang_dt,status)
    uang=get_uang_shift(id_kar,shift)
    row=[id_kar,nama,tgl_str,jm,jp,jk,jl,l1,l2,shift,ket,status,uang]
    existing=absen_df[(absen_df['ID KARYAWAN']==id_kar)&(absen_df['TANGGAL']==tgl_str)]
    if not existing.empty:
        rn=existing.index[0]+2
        ws_absen.update(f'A{rn}:M{rn}',[row])
    else: ws_absen.insert_row(row,2)
    load_data.clear()

# UI
menu=st.tabs(["📝 ABSEN","✏️ EDIT","⚙️ ADMIN","📊 REKAP"])
with menu[0]:
    id_in=st.text_input("ID Karyawan").strip().zfill(8)
    nama=""
    if id_in:
        if id_in in db_df['ID KARYAWAN'].values:
            nama=db_df[db_df['ID KARYAWAN']==id_in]['NAMA KARYAWAN'].values[0]
            st.success(f"✅ {nama}")
        else: st.error("ID tidak ada")
    tgl=st.date_input("Tanggal",datetime.now())
    colA,colB=st.columns(2)
    with colA:
        st.write("**Status Ganti Hari:**")
        status_pilih=st.selectbox("Pilih Status", ["H","GH","GHS","I","S","C","TL","A"], format_func=lambda x: {"H":"H - HADIR","GH":"GH - GANTI HARI (7 jam)","GHS":"GHS - GANTI HARI SABTU (5 jam)","I":"IZIN","S":"SAKIT","C":"CUTI","TL":"TUKAR LIBUR","A":"ALFA"}[x])
    with colB:
        jam_masuk=st.time_input("Jam Masuk",datetime.now().time())
        jam_pulang=st.time_input("Jam Pulang",datetime.now().time())
    if st.button("💾 SIMPAN ABSEN",type="primary",use_container_width=True,disabled=not nama):
        masuk_dt=datetime.combine(tgl,jam_masuk)
        pulang_dt=datetime.combine(tgl,jam_pulang)
        upsert_absen(id_in,masuk_dt,pulang_dt,nama,status_pilih,sudah_pulang=True)
        st.success(f"✅ {status_pilih} tersimpan - Lembur bulat no koma!"); st.rerun()

with menu[2]:
    if st.button("🔥 FIX BULAT NO KOMA + GH GHS (Data di SS)",type="primary",use_container_width=True):
        all_vals=ws_absen.get_all_values()
        for i,row in enumerate(all_vals[1:],start=2):
            try:
                if len(row)<5 or not row[3] or not row[4]: continue
                tgl=datetime.strptime(row[2],'%Y-%m-%d')
                masuk=datetime.strptime(row[3],'%H:%M:%S')
                pulang=datetime.strptime(row[4],'%H:%M:%S')
                masuk_dt=datetime.combine(tgl,masuk.time())
                pulang_dt=datetime.combine(tgl,pulang.time())
                if pulang_dt<masuk_dt: pulang_dt+=timedelta(days=1)
                total=(pulang_dt-masuk_dt).total_seconds()/3600-1.0
                is_sabtu=tgl.weekday()==5
                is_minggu=tgl.weekday()==6
                is_merah=row[2] in LIBUR_NASIONAL
                stat=row[11] if len(row)>11 else "H"
                jk,jl,l15,l20=hitung_lembur_bulat(total,is_sabtu,is_minggu,is_merah,stat)
                ws_absen.update(f'F{i}:I{i}',[[jk,jl,l15,l20]])
            except: pass
        st.success("✅ Semua udah bulat! 2.13 jadi 2, 7.27 jadi 7"); load_data.clear(); st.rerun()

with menu[3]:
    st.dataframe(absen_df,use_container_width=True,height=600)
