import streamlit as st, gspread, pandas as pd, requests, math, calendar
from datetime import datetime, timedelta, date, timezone
from google.oauth2.service_account import Credentials
from icalendar import Calendar
import streamlit.components.v1 as components
from fpdf import FPDF

WIB = timezone(timedelta(hours=7))
st.set_page_config(page_title="SMART HR SYSTEM", layout="wide", page_icon="⚡")

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
        absen['KETERANGAN']=absen['KETERANGAN'].astype(str)
        absen['STATUS']=absen['STATUS'].astype(str)
        absen['JAM MASUK']=absen['JAM MASUK'].astype(str)
        absen['JAM PULANG']=absen['JAM PULANG'].astype(str)
    return db,absen,col_uang
db_df,absen_df,COL_UANG_SHIFT=load_data()

def is_missing(jam): return str(jam).strip() in ["","0","0.00","00:00:00","nan","None","NaT"]
def is_libur_row(row):
    ket=str(row.get('KETERANGAN','')).upper()
    status=str(row.get('STATUS','')).upper()
    return status=='L' or 'MINGGU' in ket or 'LIBUR' in ket
def is_undefined_row(row):
    if is_libur_row(row): return False
    jm_missing=is_missing(row.get('JAM MASUK',''))
    jp_missing=is_missing(row.get('JAM PULANG',''))
    ket=str(row.get('KETERANGAN','')).upper()
    return ket=='UNDEFINED' or jm_missing or jp_missing

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
    # FIX SHIFT S2 - 14:00 sd 21:59 auto S2 biar 14:54 kebaca S2
    hm=masuk_dt.hour + masuk_dt.minute/60.0
    if 6 <= hm < 14: base='S1'
    elif 14 <= hm < 22: base='S2'
    else: base='S3'
    shift=status_final if status_final in ['A','L'] else f"H-{base}" if jam_float<11.5 else f"H-LS1" if base=='S1' else "H-LS2"
    return jk,jl,l15,l20,shift,ket,status_final

def get_periode(bulan,tahun,mode):
    if mode=="Bulan Kalender": return date(tahun,bulan,1), date(tahun,bulan,calendar.monthrange(tahun,bulan)[1])
    else:
        if bulan==1: return date(tahun-1,12,21), date(tahun,1,20)
        else: return date(tahun,bulan-1,21), date(tahun,bulan,20)

def create_payroll_pdf(id_kar, nama, periode_awal, periode_akhir, hadir_valid, uang_makan, uang_transport, total_lembur, uang_lembur, shift_malam, uang_shift, hari_lembur, uang_makan_lembur, total_pendapatan, total_potongan, total_gaji, jml_undefined, jml_libur):
    pdf = FPDF(); pdf.add_page(); pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Arial", 'B', 14); pdf.cell(0, 10, 'SLIP GAJI - SMART HR SYSTEM', 0, 1, 'C')
    pdf.set_font("Arial", '', 9); pdf.cell(0, 5, f'Periode: {periode_awal} s/d {periode_akhir} | Hadir {hadir_valid} | UNDEFINED {jml_undefined} | Libur {jml_libur}', 0, 1, 'C')
    pdf.ln(2); pdf.set_font("Arial", 'B', 10); pdf.cell(0, 6, f'ID: {id_kar} - {nama}', 0, 1, 'L'); pdf.ln(2)
    pdf.set_font("Arial", 'B', 10); pdf.set_fill_color(0,100,0); pdf.set_text_color(255,255,255); pdf.cell(0, 7, ' PENDAPATAN', 1, 1, 'L', True)
    pdf.set_text_color(0,0,0); pdf.set_font("Arial", '', 9)
    tunj_loyal=3500; jkk=12606; jkm=15758; jht_per=194357; jp_per=105058; bpjs_per=210116
    pend=[(f"Gaji Pokok", 5252909),(f"Premi Hadir", 50000),(f"Uang Makan ({hadir_valid} Hari x 9500)", uang_makan),(f"Uang Transport", uang_transport),(f"Uang Lembur ({total_lembur:.2f} Jam x 30000)", int(uang_lembur)),(f"Uang Shift ({shift_malam} Hari x 2187)", int(uang_shift)),(f"Uang Makan Lembur ({hari_lembur} Hari x 9500)", int(uang_makan_lembur)),(f"Tunjangan Loyalitas", tunj_loyal),(f"JKK", jkk),(f"JKM", jkm),(f"JHT Perusahaan", jht_per),(f"JP Perusahaan", jp_per),(f"BPJS Kes Perusahaan", bpjs_per),]
    for n,v in pend: pdf.cell(115, 6, f" {n}", border=1); pdf.cell(0, 6, f" Rp {v:,}", border=1, ln=1)
    pdf.set_font("Arial", 'B', 9); pdf.set_fill_color(220,220,220); pdf.cell(115, 7, ' TOTAL PENDAPATAN', 1, 0, 'L', True); pdf.cell(0, 7, f' Rp {int(total_pendapatan):,}', 1, 1, 'L', True); pdf.ln(3)
    pdf.set_font("Arial", 'B', 10); pdf.set_fill_color(150,0,0); pdf.set_text_color(255,255,255); pdf.cell(0, 7, ' POTONGAN', 1, 1, 'L', True)
    pdf.set_text_color(0,0,0); pdf.set_font("Arial", '', 9); jht_tk=105058; jp_tk=52529; bpjs_kar=52529
    pot=[(f"JKK", jkk),(f"JKM", jkm),(f"JHT Perusahaan", jht_per),(f"JP Perusahaan", jp_per),(f"BPJS Kes Perusahaan", bpjs_per),(f"JHT TK", jht_tk),(f"JP TK", jp_tk),(f"BPJS Kes Karyawan", bpjs_kar),]
    for n,v in pot: pdf.cell(115, 6, f" {n}", border=1); pdf.cell(0, 6, f" Rp {v:,}", border=1, ln=1)
    pdf.set_font("Arial", 'B', 9); pdf.set_fill_color(220,220,220); pdf.cell(115, 7, ' TOTAL POTONGAN', 1, 0, 'L', True); pdf.cell(0, 7, f' Rp {int(total_potongan):,}', 1, 1, 'L', True); pdf.ln(4)
    pdf.set_font("Arial", 'B', 12); pdf.set_fill_color(0,0,0); pdf.set_text_color(255,255,0); pdf.cell(115, 9, ' TOTAL GAJI BERSIH', 1, 0, 'L', True); pdf.cell(0, 9, f' Rp {int(total_gaji):,}', 1, 1, 'L', True)
    return bytes(pdf.output())

tab1,tab2,tab3,tab4,tab5=st.tabs(["ABSEN","EDIT","ADMIN","REKAP","PAYROLL"])

with tab1:
    components.html("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@900&display=swap');
.clock-box{ background: radial-gradient(circle at center, #111 0%, #000 100%); border-radius:18px; padding:22px; border:1.5px solid #222; text-align:center; box-shadow: 0 0 40px rgba(0,0,0,1), inset 0 1px 0 rgba(255,255,255,0.1); }
.smart-title{ font-family:'Orbitron', sans-serif; font-size:20px; font-weight:900; color:#e5e7eb; letter-spacing:3px; display:flex; align-items:center; justify-content:center; gap:12px; }
.petir{ color:#facc15; font-size:28px; text-shadow:0 0 10px #facc15,0 0 20px #eab308; animation:petirGlow 1s infinite alternate; }
 @keyframes petirGlow{from{text-shadow:0 0 10px #facc15;} to{text-shadow:0 0 20px #fde047,0 0 40px #facc15; transform:scale(1.1);} }
.label-blink{ color:#facc15; font-size:10px; letter-spacing:4px; font-weight:800; margin:10px 0 8px 0; animation:blinkText 0.8s infinite steps(1); }
 @keyframes blinkText{0%{opacity:1;}50%{opacity:0.3;}}
 #clock{ font-family:'Orbitron', monospace; font-size:50px; font-weight:900; letter-spacing:6px; color:#22ff88; text-shadow:0 0 12px #22c55e,0 0 25px #16a34a; }
 #date{ color:#666; font-size:12px; margin-top:8px; }
.dot{ display:inline-block; width:8px; height:8px; background:#facc15; border-radius:50%; box-shadow:0 0 10px #facc15; animation:dotBlink 0.8s infinite steps(1); margin-right:6px; }
 @keyframes dotBlink{0%{opacity:1;}50%{opacity:0.2;}}
    </style>
    <div class="clock-box">
        <div class="smart-title"><span class="petir">⚡</span> SMART HR SYSTEM <span class="petir">⚡</span></div>
        <div class="label-blink"><span class="dot"></span>WAKTU REALTIME WIB</div>
        <div id="clock">--:--:--</div>
        <div id="date">Loading...</div>
    </div>
    <script>
    function updateClock(){
        const now = new Date();
        const wib = new Date(now.toLocaleString('en-US', {timeZone: 'Asia/Jakarta'}));
        document.getElementById('clock').innerText = String(wib.getHours()).padStart(2,'0')+':'+String(wib.getMinutes()).padStart(2,'0')+':'+String(wib.getSeconds()).padStart(2,'0');
        document.getElementById('date').innerText = wib.toLocaleDateString('id-ID', {weekday:'long', day:'2-digit', month:'long', year:'numeric'})+' WIB';
    }
    setInterval(updateClock,1000); updateClock();
    function speak(t){ try{ window.speechSynthesis.cancel(); const u=new SpeechSynthesisUtterance(t); u.lang='en-US'; u.rate=0.95; u.pitch=1.1; u.volume=1; const vs=window.speechSynthesis.getVoices(); const f=vs.find(v=>v.name.toLowerCase().includes('female')||v.name.includes('Samantha')||v.name.includes('Google US English')); if(f) u.voice=f; window.speechSynthesis.speak(u);}catch(e){} }
    window.speechSynthesis.getVoices(); window.speechSynthesis.onvoiceschanged=()=>{window.speechSynthesis.getVoices();};
    try{
        const pd=window.parent.document;
        function attach(){ pd.querySelectorAll('button').forEach(b=>{ const txt=b.innerText.toUpperCase(); if(txt.includes('ABSEN MASUK')&&!b.dataset.voice){ b.dataset.voice='in'; b.addEventListener('click',()=>setTimeout(()=>speak('Login successfully'),200)); } if(txt.includes('PULANG SEKARANG')&&!b.dataset.voice){ b.dataset.voice='out'; b.addEventListener('click',()=>setTimeout(()=>speak('Logout successfully'),200)); } }); }
        setInterval(attach,500);
    }catch(e){}
    </script>
    """, height=165)

    id_in=st.text_input("ID ABSEN", value="01213027").strip().zfill(8)
    nama=db_df[db_df['ID KARYAWAN']==id_in]['NAMA KARYAWAN'].values[0] if id_in in db_df['ID KARYAWAN'].values else ""
    if nama: st.success(f"👋 {nama}")
    ubah_manual=st.checkbox("✏️ Ubah Tanggal & Jam Manual?", value=False)
    today_wib = now_wib().date()
    row_today=absen_df[(absen_df['ID KARYAWAN']==id_in)&(absen_df['TANGGAL MASUK']==today_wib.strftime('%Y-%m-%d'))&(~absen_df['JAM MASUK'].apply(is_missing))] if not absen_df.empty else pd.DataFrame()
    if row_today.empty:
        if ubah_manual:
            c1,c2=st.columns(2); tgl_m=c1.date_input("TANGGAL MASUK", value=today_wib, key="tgl_m"); jam_m=c2.time_input("JAM MASUK", value=now_wib().time(), key="jam_m")
        else: tgl_m=today_wib; jam_m=now_wib().time()
        if st.button("🟢 ABSEN MASUK", type="primary", use_container_width=True):
            if not ubah_manual: klik_wib=now_wib(); tgl_m=klik_wib.date(); jam_m=klik_wib.time()
            row=[id_in,nama,tgl_m.strftime('%Y-%m-%d'),datetime.combine(tgl_m, jam_m).strftime('%H:%M:%S'),"","","0.00","0.00","0.00","0.00","-","UNDEFINED","H","0"]
            ws_absen.insert_row(row,2); load_data.clear(); st.balloons(); st.rerun()
    else:
        r=row_today.iloc[0]
        if is_missing(r['JAM PULANG']):
            st.warning(f"✅ Masuk {r['TANGGAL MASUK']} {r['JAM MASUK']} - UNDEFINED")
            if ubah_manual:
                c1,c2=st.columns(2); tgl_p=c1.date_input("TANGGAL PULANG", value=today_wib, key="tgl_p"); jam_p=c2.time_input("JAM PULANG", value=now_wib().time(), key="jam_p")
            else: tgl_p=today_wib; jam_p=now_wib().time()
            if st.button("🔴 PULANG SEKARANG", type="primary", use_container_width=True):
                if not ubah_manual:
                    klik_wib=now_wib(); tgl_p=klik_wib.date(); jam_p=klik_wib.time()
                    try:
                        if jam_p < datetime.strptime(r['JAM MASUK'], '%H:%M:%S').time(): tgl_p = tgl_p + timedelta(days=1)
                    except: pass
                masuk_dt=datetime.combine(datetime.strptime(r['TANGGAL MASUK'], '%Y-%m-%d').date(), datetime.strptime(r['JAM MASUK'], '%H:%M:%S').time())
                pulang_dt=datetime.combine(tgl_p, jam_p)
                jk,jl,l15,l20,shift,ket,status_final=hitung_final(masuk_dt,pulang_dt,r['STATUS'])
                uang=get_uang_shift(id_in, shift, float(jl))
                rn=row_today.index[0]+2
                ws_absen.update(f'C{rn}:N{rn}', [[r['TANGGAL MASUK'],r['JAM MASUK'],tgl_p.strftime('%Y-%m-%d'),jam_p.strftime('%H:%M:%S'),jk,jl,l15,l20,shift,ket,status_final,uang]])
                load_data.clear(); st.success(f"PULANG {jk} jam"); st.balloons(); st.rerun()
        else: st.success(f"✅ {r['TANGGAL MASUK']} {r['JAM MASUK']} → {r['TANGGAL PULANG']} {r['JAM PULANG']}")

with tab3:
    st.markdown("#### ADMIN - PERBAIKAN DATA")
    if st.button("⚡ BERSIHKAN DAN PERBAIKI DATA", type="primary", use_container_width=True):
        with st.spinner("Lagi bersihin + benerin shift S2..."):
            vals=ws_absen.get_all_values()
            # 1. Bersihkan data rusak
            hapus=[]
            for i,r in enumerate(vals[1:], start=2):
                if len(r)<6: continue
                jm=str(r[3]).strip() if len(r)>3 else ""
                jp=str(r[5]).strip() if len(r)>5 else ""
                ket=str(r[11]).strip() if len(r)>11 else ""
                stat=str(r[12]).strip() if len(r)>12 else ""
                if jm=="" and jp=="" and ket=="" and stat=="": hapus.append(i)
            if hapus:
                for row_idx in sorted(hapus, reverse=True): ws_absen.delete_rows(row_idx)
                st.toast(f"Hapus {len(hapus)} baris kosong")

            # 2. Perbaiki shift yang salah (khususnya tgl 07 yang 14:54 jadi S2)
            vals=ws_absen.get_all_values()
            fixed=0
            for i,r in enumerate(vals[1:], start=2):
                if len(r)<13: continue
                try:
                    id_k=r[0]; tgl_m=r[2]; jam_m=r[3]; tgl_p=r[4] if len(r)>4 else tgl_m; jam_p=r[5] if len(r)>5 else ""; stat=r[12] if len(r)>12 else "H"
                    if not jam_m or is_missing(jam_m) or not jam_p or is_missing(jam_p): continue
                    masuk_dt=datetime.strptime(f"{tgl_m} {jam_m}", "%Y-%m-%d %H:%M:%S")
                    pulang_dt=datetime.strptime(f"{tgl_p} {jam_p}", "%Y-%m-%d %H:%M:%S")
                    jk,jl,l15,l20,shift_baru,ket_baru,status_final=hitung_final(masuk_dt,pulang_dt,stat)
                    shift_lama=r[10] if len(r)>10 else ""
                    if shift_baru!= shift_lama:
                        uang=get_uang_shift(id_k, shift_baru, float(jl) if jl else 0)
                        ws_absen.update(f'G{i}:N{i}', [[jk,jl,l15,l20,shift_baru,ket_baru,status_final,uang]])
                        fixed+=1
                except: continue
            load_data.clear()
            st.success(f"Selesai! Hapus {len(hapus)} baris kosong | Perbaiki {fixed} shift (tgl 07 jadi H-S2) ✅")
            st.balloons()

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
        df_f=absen_df[(absen_df['TGL_DT']>=pd.to_datetime(awal_r))&(absen_df['TGL_DT']<=pd.to_datetime(akhir_r))].copy()
        if not df_f.empty:
            st.error(f"UNDEFINED {len(df_f[df_f.apply(is_undefined_row, axis=1)])} | LIBUR {len(df_f[df_f.apply(is_libur_row, axis=1)])}")
            st.dataframe(df_f.sort_values('TGL_DT',ascending=False), use_container_width=True, height=600)

with tab5:
    st.markdown("#### PAYROLL")
    mode_g=st.radio("Mode Gaji", ["21-20 Payroll","Bulan Kalender"], horizontal=True, key="mode_g")
    c1,c2=st.columns(2)
    with c1: bulan_g=st.selectbox("Bulan Gaji", list(range(1,13)), index=now_wib().month-1, key="bulan_g")
    with c2: tahun_g=st.number_input("Tahun Gaji", 2020, 2030, now_wib().year, key="tahun_g")
    awal_g,akhir_g=get_periode(bulan_g,tahun_g,mode_g)
    st.info(f"Periode: {awal_g} s/d {akhir_g}")
    id_gaji=st.selectbox("Karyawan", db_df['ID KARYAWAN'].tolist())
    if st.button("HITUNG PAYROLL", type="primary", use_container_width=True):
        df_g=absen_df[(absen_df['ID KARYAWAN']==id_gaji)&(absen_df['TGL_DT']>=pd.to_datetime(awal_g))&(absen_df['TGL_DT']<=pd.to_datetime(akhir_g))].copy()
        if not df_g.empty:
            jml_undefined=len(df_g[df_g.apply(is_undefined_row, axis=1)]); jml_libur=len(df_g[df_g.apply(is_libur_row, axis=1)])
            df_complete=df_g[~df_g.apply(is_undefined_row, axis=1)&~df_g.apply(is_libur_row, axis=1)].copy()
            df_complete['SHIFT']=df_complete['SHIFT'].fillna('').astype(str)
            hadir_valid=len(df_complete[df_complete['STATUS']=='H'])
            total_lembur=pd.to_numeric(df_complete['JAM LEMBUR'],errors='coerce').fillna(0).sum()
            shift_malam=len(df_complete[df_complete['SHIFT'].str.contains('S2|S3|LS1|LS2', na=False)])
            hari_lembur=len(df_complete[pd.to_numeric(df_complete['JAM LEMBUR'],errors='coerce').fillna(0)>0])
            uang_makan=hadir_valid*9500; uang_transport=hadir_valid*0; uang_lembur=total_lembur*30000; uang_shift=shift_malam*2187; uang_makan_lembur=hari_lembur*9500
            gaji_pokok=5252909; tunj_loyal=3500; jkk=12606; jkm=15758; jht_per=194357; jp_per=105058; bpjs_per=210116
            total_pend=gaji_pokok+50000+uang_makan+uang_transport+uang_lembur+uang_shift+uang_makan_lembur+tunj_loyal+jkk+jkm+jht_per+jp_per+bpjs_per
            jht_tk=105058; jp_tk=52529; bpjs_kar=52529; total_pot=jkk+jkm+jht_per+jp_per+bpjs_per+jht_tk+jp_tk+bpjs_kar; total_gaji=total_pend-total_pot
            st.session_state['payroll_data']={'id_kar':id_gaji,'nama':db_df[db_df['ID KARYAWAN']==id_gaji]['NAMA KARYAWAN'].values[0],'awal':awal_g,'akhir':akhir_g,'hadir_valid':hadir_valid,'uang_makan':uang_makan,'uang_transport':uang_transport,'total_lembur':total_lembur,'uang_lembur':uang_lembur,'shift_malam':shift_malam,'uang_shift':uang_shift,'hari_lembur':hari_lembur,'uang_makan_lembur':uang_makan_lembur,'total_pendapatan':total_pend,'total_potongan':total_pot,'total_gaji':total_gaji,'jml_undefined':jml_undefined,'jml_libur':jml_libur}
            st.session_state['payroll_ready']=True
            c1,c2,c3,c4=st.columns(4); c1.metric("Hadir", hadir_valid); c2.metric("UNDEFINED", jml_undefined); c3.metric("Libur", jml_libur); c4.metric("TOTAL", f"Rp {int(total_gaji):,}")
    if st.session_state.get('payroll_ready'):
        d=st.session_state['payroll_data']
        pdf_bytes=create_payroll_pdf(d['id_kar'],d['nama'],d['awal'],d['akhir'],d['hadir_valid'],d['uang_makan'],d['uang_transport'],d['total_lembur'],d['uang_lembur'],d['shift_malam'],d['uang_shift'],d['hari_lembur'],d['uang_makan_lembur'],d['total_pendapatan'],d['total_potongan'],d['total_gaji'],d['jml_undefined'],d['jml_libur'])
        st.download_button(label="📄 DOWNLOAD PDF", data=pdf_bytes, file_name=f"PAYROLL_{d['id_kar']}_{d['awal']}_{d['akhir']}.pdf", mime="application/pdf", type="primary", use_container_width=True)

with tab2:
    st.markdown("#### EDIT")
    if "login" not in st.session_state: st.session_state.login=False
    if not st.session_state.login:
        pw=st.text_input("Password", type="password")
        if st.button("LOGIN"):
            if pw=="admin123": st.session_state.login=True; st.rerun()
    else:
        if st.button("LOGOUT"): st.session_state.login=False; st.rerun()
        id_edit=st.text_input("ID EDIT", value="01213027").strip().zfill(8)
        data_kar=absen_df[absen_df['ID KARYAWAN']==id_edit].sort_values('TGL_DT', ascending=False)
        if not data_kar.empty:
            pilih_tgl=st.selectbox("Pilih Tanggal", data_kar['TANGGAL MASUK'].tolist())
            row=data_kar[data_kar['TANGGAL MASUK']==pilih_tgl].iloc[0]
            st.info(f"{row['TANGGAL MASUK']} {row['JAM MASUK']} → {row['JAM PULANG']} | {row['KETERANGAN']}")
            c1,c2=st.columns(2)
            with c1: tgl_e=st.date_input("Tgl Masuk", pd.to_datetime(row['TANGGAL MASUK']).date()); jm_e=st.time_input("Jam Masuk", datetime.strptime(row['JAM MASUK'], '%H:%M:%S').time() if not is_missing(row['JAM MASUK']) else now_wib().time())
            with c2: tgl_pe=st.date_input("Tgl Pulang", pd.to_datetime(row['TANGGAL PULANG']).date() if not is_missing(row['TANGGAL PULANG']) else pd.to_datetime(row['TANGGAL MASUK']).date()); jp_e=st.time_input("Jam Pulang", datetime.strptime(row['JAM PULANG'], '%H:%M:%S').time() if not is_missing(row['JAM PULANG']) else now_wib().time())
            st_e=st.selectbox("Status", ["H","GH","GHS","A","L","I","S","TL"])
            if st.button("UPDATE", type="primary", use_container_width=True):
                masuk_dt=datetime.combine(tgl_e, jm_e); pulang_dt=datetime.combine(tgl_pe, jp_e)
                jk,jl,l15,l20,shift,ket,status_final=hitung_final(masuk_dt,pulang_dt,st_e)
                uang=get_uang_shift(id_edit, shift, float(jl))
                rn=data_kar[data_kar['TANGGAL MASUK']==pilih_tgl].index[0]+2
                ws_absen.update(f'A{rn}:N{rn}', [[id_edit, row['NAMA KARYAWAN'], tgl_e.strftime('%Y-%m-%d'), jm_e.strftime('%H:%M:%S'), tgl_pe.strftime('%Y-%m-%d'), jp_e.strftime('%H:%M:%S'), jk,jl,l15,l20,shift,ket,status_final,uang]])
                load_data.clear(); st.success("Updated"); st.rerun()
