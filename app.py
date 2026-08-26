def get_shift_info(masuk_dt, is_sabtu=False):
    jam = masuk_dt.hour
    if is_sabtu: # JAM SHIFT KHUS SABTU FINAL
        if 7 <= jam < 12: return "SHIFT 1 SABTU", masuk_dt.replace(hour=12, minute=0, second=0)
        elif 12 <= jam < 17: return "SHIFT 2 SABTU", masuk_dt.replace(hour=17, minute=0, second=0)
        else: return "SHIFT 3 SABTU", masuk_dt.replace(hour=23, minute=0, second=0) # INI YG DIBENERIN JADI 23
    else: # JAM SHIFT HARI BIASA
        if 7 <= jam < 15: return "SHIFT 1", masuk_dt.replace(hour=15, minute=0, second=0)
        elif 15 <= jam < 23: return "SHIFT 2", masuk_dt.replace(hour=23, minute=0, second=0)
        else:
            efektif_pulang = masuk_dt.replace(hour=7, minute=0, second=0)
            if jam >= 23: efektif_pulang += timedelta(days=1)
            return "SHIFT 3", efektif_pulang
