"""check_video.py - test workflow ka checker (sab 22 tools par ek jaisa).

Ek tool ki video check:   python check_video.py output <slug>   -> output/check.json
Sab ka summary:           python check_video.py --summary all_dir  -> markdown (stdout)

FAIL = aam admi ko nazar aane wali ghalti. WARN = dhyan do, par video theek ho sakti hai.
"""
import json, re, subprocess, sys
from pathlib import Path

W, H = 1080, 1920
REC_Y, REC_H = 170, 1380            # video.py ke REC_Y / REC_MAX_H se match
MIN_S, MAX_S = 45.0, 60.0
MEAN_MIN, MEAN_MAX, PEAK_MAX = -23.0, -16.0, -1.0
EDGE_LUMA = 48                       # navy background is se kam roshan hota hai
EDGE_FRAC = 0.02                     # edge ki patti ka itna hissa roshan ho to "tool kata hua"


def sh(cmd, binary=False):
    r = subprocess.run(cmd, capture_output=True)
    return r.stdout if binary else (r.stdout + r.stderr).decode("utf-8", "ignore")


def probe(video):
    j = json.loads(sh(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams",
                       "-show_format", str(video)]))
    v = next((s for s in j["streams"] if s["codec_type"] == "video"), {})
    has_audio = any(s["codec_type"] == "audio" for s in j["streams"])
    return int(v.get("width", 0)), int(v.get("height", 0)), float(j["format"].get("duration", 0)), has_audio


def loudness(video):
    t = sh(["ffmpeg", "-i", str(video), "-af", "volumedetect", "-vn", "-f", "null", "-"])
    m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", t)
    x = re.search(r"max_volume:\s*(-?[\d.]+) dB", t)
    return (float(m.group(1)) if m else None, float(x.group(1)) if x else None)


def bright_fraction(video, t, crop):
    """crop = 'w:h:x:y'. Us patti ke kitne hisse pixel navy se roshan hain."""
    data = sh(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
               "-vf", f"crop={crop},format=gray", "-f", "rawvideo", "-"], binary=True)
    if not data:
        return 0.0
    return sum(1 for b in data if b > EDGE_LUMA) / len(data)


def edge_cut(video, dur):
    """Recording ke upar/neeche/daayen/baayen kinare par tool ka roshan hissa ho to wo kata hua hai."""
    times = [t for t in (2, 8, 14, 20, 26, 32, 38, 44) if t < dur - 3]
    bands = {
        "upar": f"{W}:6:0:{REC_Y}",
        "neeche": f"{W}:6:0:{REC_Y + REC_H - 6}",
        "baayen": f"4:{REC_H - 200}:0:{REC_Y + 100}",
        "daayen": f"4:{REC_H - 200}:{W - 4}:{REC_Y + 100}",
    }
    hit = set()
    for t in times:
        for name, crop in bands.items():
            if bright_fraction(video, t, crop) > EDGE_FRAC:
                hit.add(name)
    return sorted(hit)


def check_one(out, slug):
    out = Path(out)
    res = {"slug": slug, "fail": [], "warn": [], "info": {}}
    rep = {}
    if (out / "report.json").exists():
        rep = json.loads((out / "report.json").read_text())
    video = out / "short.mp4"
    if not video.exists():
        res["fail"].append("video bani hi nahi: " + str(rep.get("skipped", "main.py fail/skip hua")))
        return res
    w, h, dur, has_audio = probe(video)
    res["info"].update(size=f"{w}x{h}", seconds=round(dur, 1))
    if (w, h) != (W, H):
        res["fail"].append(f"size {w}x{h} (1080x1920 chahiye)")
    if not (MIN_S <= dur <= MAX_S):
        res["fail"].append(f"length {dur:.1f}s (45-60s chahiye)")
    if not has_audio:
        res["fail"].append("awaaz nahi hai")
    else:
        mean, peak = loudness(video)
        res["info"].update(mean_db=mean, peak_db=peak)
        if mean is None or not (MEAN_MIN <= mean <= MEAN_MAX):
            res["fail"].append(f"awaaz ki loudness mean {mean} dB (-23 se -16 chahiye)")
        if peak is not None and peak > PEAK_MAX:
            res["fail"].append(f"awaaz peak {peak} dB (clipping ka khatra)")
    cut = edge_cut(video, dur)
    if cut:
        res["fail"].append("tool kata hua lagta hai: " + ", ".join(cut))
    # script: LLM ki pass hui ya fallback chali
    log = out / "script_log.json"
    if log.exists():
        att = json.loads(log.read_text())
        passed = [a for a in att if a.get("ok")]
        res["info"]["script_attempts"] = len(att)
        if not passed:
            res["warn"].append("fallback script chali (LLM script policy mein fail hui)")
            res["info"]["why_fallback"] = [i for a in att for i in (a.get("issues") or [])][:4]
        elif len(att) > 1:
            res["warn"].append(f"script {len(att)} koshish mein pass hui")
    else:
        res["warn"].append("script_log.json nahi mili")
    return res


def summary(root):
    rows = []
    for f in sorted(Path(root).glob("*/check.json")):
        rows.append(json.loads(f.read_text()))
    n_fail = sum(1 for r in rows if r["fail"])
    n_warn = sum(1 for r in rows if not r["fail"] and r["warn"])
    lines = [f"## 22 tools video check: {len(rows)} mile | FAIL {n_fail} | WARN {n_warn} | OK {len(rows) - n_fail - n_warn}", "",
             "| Tool | Nateeja | Length | Awaaz mean | Masla |", "|---|---|---|---|---|"]
    for r in rows:
        st = "FAIL" if r["fail"] else ("WARN" if r["warn"] else "OK")
        i = r["info"]
        issues = "; ".join(r["fail"] + r["warn"]) or "-"
        lines.append(f"| {r['slug']} | {st} | {i.get('seconds', '-')}s | {i.get('mean_db', '-')} | {issues} |")
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--summary":
        print(summary(sys.argv[2]))
    else:
        out, slug = (sys.argv[1] if len(sys.argv) > 1 else "output"), (sys.argv[2] if len(sys.argv) > 2 else "?")
        r = check_one(out, slug)
        Path(out).mkdir(parents=True, exist_ok=True)
        (Path(out) / "check.json").write_text(json.dumps(r, indent=2, ensure_ascii=False))
        print(json.dumps(r, indent=2, ensure_ascii=False))
