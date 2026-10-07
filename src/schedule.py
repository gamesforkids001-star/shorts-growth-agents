import datetime, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
START_FILE = ROOT / "state" / "start.json"

# Global timing (UTC). Workflow ki cron isi se match karti hai.
#  00 UTC = US shaam (8 PM ET / 5 PM PT)      | 04 UTC = South Asia subah
#  08 UTC = Europe subah, South Asia dopahar  | 12 UTC = US subah, Europe dopahar
#  16 UTC = US lunch, Europe shaam, Pak raat  | 20 UTC = US dopahar, Europe raat
SLOT_HOURS_UTC = [0, 4, 8, 12, 16, 20]
# Kitni videos/day ho to kaun se slots chalenge (har baar sirf ek slot barhta hai)
ACTIVE = {
    1: [4],
    2: [2, 4],
    3: [0, 2, 4],
    4: [0, 2, 4, 5],
    5: [0, 2, 3, 4, 5],
    6: [0, 1, 2, 3, 4, 5],
}


def today_utc():
    return datetime.datetime.now(datetime.timezone.utc).date()


def get_start():
    try:
        return datetime.date.fromisoformat(json.loads(START_FILE.read_text())["start_date"])
    except Exception:
        return None


def set_start_if_missing():
    if get_start() is None:
        START_FILE.write_text(json.dumps({"start_date": today_utc().isoformat()}))


def quota(start, today, ramp_days=15, max_per_day=6):
    if start is None:
        return 1
    return max(1, min(max_per_day, 1 + (today - start).days // ramp_days))


def current_slot():
    now = datetime.datetime.now(datetime.timezone.utc)
    h = now.hour + now.minute / 60
    def dist(i):
        d = abs(SLOT_HOURS_UTC[i] - h)
        return min(d, 24 - d)
    return min(range(len(SLOT_HOURS_UTC)), key=dist)


def _posted(entry):
    """Slot tab 'done' maana jaye ga jab kam az kam ek platform par post hui ho
    (ya purani entry ho jisme results hi nahi)."""
    res = entry.get("results")
    if res is None:
        return True
    return any(str(v).startswith("posted") for v in res.values())


def slot_done(history, today, slot):
    return any(h.get("date") == today.isoformat() and h.get("slot") == slot and _posted(h)
               for h in history)


def should_run(history, cfg):
    """Returns (run?, slot, quota, reason).
    Catch-up: aaj ke active slots jinka waqt guzar chuka hai aur post nahi hui,
    unme se sab se purana slot chalta hai. Is liye late ya drop hua run agle run mein pura ho jata hai."""
    now = datetime.datetime.now(datetime.timezone.utc)
    today = now.date()
    h = now.hour + now.minute / 60
    q = quota(get_start(), today, cfg.get("ramp_days", 15), cfg.get("max_per_day", 6))
    due = [i for i in ACTIVE[q] if SLOT_HOURS_UTC[i] <= h]
    if not due:
        return False, -1, q, f"aaj {q} video/day hai, abhi kisi active slot ka waqt nahi hua"
    pending = [i for i in due if not slot_done(history, today, i)]
    if not pending:
        return False, -1, q, "aaj ke saare due slots ki video ho chuki hai"
    slot = pending[0]
    late = " (catch-up: pichla slot reh gaya tha)" if len(pending) > 1 or SLOT_HOURS_UTC[slot] < int(h) else ""
    return True, slot, q, "ok" + late
