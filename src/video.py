import asyncio, json, math, os, re, subprocess
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# Layout: oopar tool ka naam, beech mein tool (screen recording), neeche captions
REC_Y = 170          # recording kahan se shuru ho
REC_MAX_W = 1080     # record.py ke VIEW_W se match
REC_MAX_H = 1380     # record.py ke VIEW_H se match (170 + 1380 = 1550 tak)
CAP_CY = 1730        # captions/CTA ka center
CAP_WORDS = 11       # ek caption mein zyada se zyada itne alfaaz
CAP_FONT = 62        # sab captions ka ek jaisa font size (pehle kabhi kabhi chhota ho jata tha)
CAP_MAX_LINES = 3    # caption dabbe mein zyada se zyada itni lines

CTA_TEXT = "Link in description & profile"
CTA_SECS = 2.0       # aakhri itne second on-screen CTA

MIN_SECONDS = 45.0   # video 45s se chhoti na ho (chhoti ho to aakhri frame ruka kar 45s kar do)

# edge-tts ki raftaar. "+0%" = normal. (+8% karne se 100 words bhi 45s se chhoti video dete hain, is liye normal)
TTS_RATE = "+0%"

# Rang: recording ka asal background (dark navy) - patti isi rang ki hai, is liye alag nazar nahi aati
BG_TOP = (12, 16, 31)
BG_BOTTOM = (10, 17, 31)
ACCENT = (37, 99, 235)       # site ka neela rang (pill, CTA border)
CAP_BOX = (20, 30, 56, 240)  # caption ka dark-blue dabba


def _font(size):
    try:
        return ImageFont.truetype(FONT, size)
    except Exception:
        return ImageFont.load_default()


def _gradient(c1, c2):
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)))
    return img


def _wrap(draw, text, font, max_w):
    lines, cur = [], ""
    for word in text.split():
        test = (cur + " " + word).strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


_MEASURE = ImageDraw.Draw(Image.new("RGB", (4, 4)))


def _fits(text):
    """Ye text CAP_FONT par CAP_MAX_LINES lines ke andar aata hai?"""
    return len(_wrap(_MEASURE, text, _font(CAP_FONT), W - 200)) <= CAP_MAX_LINES


# Caption kahan se na kate: in lafzon par caption khatam nahi hona chahiye
_BAD_END = {"a", "an", "the", "of", "to", "in", "on", "at", "for", "with", "from", "by", "and", "or",
            "but", "is", "are", "was", "were", "be", "your", "my", "our", "its", "this", "that",
            "these", "those", "can", "will", "get", "gets", "into", "than", "as", "so", "very",
            "quite", "just", "any", "every", "each", "no", "not", "you", "it", "we", "they"}
# In lafzon se naya caption shuru ho to achha lagta hai
_GOOD_START = {"and", "but", "so", "or", "with", "without", "for", "from", "that", "which", "when",
               "while", "because", "before", "after", "then", "instead", "using", "just"}


def _cut_score(words, i, ideal):
    """words[:i] aur words[i:] ke beech cut ka score (zyada = behtar)."""
    prev, nxt = words[i - 1], words[i]
    s = -1.0 * abs(i - ideal)
    if prev.endswith((",", ";", ":")):
        s += 4
    if nxt.lower().strip(",.") in _GOOD_START:
        s += 3.5
    if prev.lower().strip(",.;:") in _BAD_END:
        s -= 5
    return s


def _split_k(words, k, max_words):
    """words ko k tukron mein todta hai (acchi hadd par: comma, 'so', 'and' se pehle)."""
    n = len(words)
    cuts, last = [], 0
    for j in range(1, k):
        ideal = round(j * n / k)
        lo = max(last + 2, ideal - 3)
        hi = min(n - 2, ideal + 3)
        # baki hisse max_words se bade na ho jayen
        lo = max(lo, n - (k - j) * max_words)
        hi = min(hi, last + max_words)
        if lo > hi:
            best = min(max(ideal, last + 1), n - 1)
        else:
            best = max(range(lo, hi + 1), key=lambda i: _cut_score(words, i, ideal))
        cuts.append(best)
        last = best
    parts, a = [], 0
    for c in cuts + [n]:
        parts.append(" ".join(words[a:c]))
        a = c
    return parts


def _split_sentence(words, max_words):
    n = len(words)
    if n <= max_words and _fits(" ".join(words)):
        return [" ".join(words)]
    k0 = max(2, math.ceil(n / max_words))
    parts = None
    for k in range(k0, max(k0, n // 2) + 1):
        parts = _split_k(words, k, max_words)
        if all(p and _fits(p) for p in parts):
            return parts
    return parts or [" ".join(words)]


def split_chunks(text, max_words=CAP_WORDS):
    """Narration ko caption tukron mein todta hai. Pehle jumle, phir lambe jumle ko
    comma / conjunction ki hadd par; 'the', 'to', 'of' jaise lafz par kabhi nahi katta.
    Har tukra CAP_FONT par CAP_MAX_LINES lines mein fit hota hai (font hamesha ek jaisa)."""
    chunks = []
    for sent in re.split(r"(?<=[.!?])\s+", text.strip()):
        words = sent.split()
        if not words:
            continue
        chunks.extend(_split_sentence(words, max_words))
    return chunks


def make_caption(text, tool_name, path):
    """Ek PNG: oopar tool ka naam (neeli pill), neeche caption (dark-blue dabba)."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f_small = _font(46)
    tw = d.textlength(tool_name, font=f_small)
    py = 40
    d.rounded_rectangle([(W - tw) / 2 - 40, py, (W + tw) / 2 + 40, py + 90], radius=45, fill=ACCENT + (255,))
    d.text(((W - tw) / 2, py + 15), tool_name, font=f_small, fill=(255, 255, 255, 255))
    size = CAP_FONT
    font = _font(size)
    lines = _wrap(d, text, font, W - 200)
    while len(lines) > CAP_MAX_LINES and size > 44:  # sirf bahut hi anokhi halat mein chhota
        size -= 4
        font = _font(size)
        lines = _wrap(d, text, font, W - 200)
    lh = int(size * 1.3)
    th = lh * len(lines)
    top = CAP_CY - th // 2 - 40
    d.rounded_rectangle([60, top, W - 60, top + th + 80], radius=40, fill=CAP_BOX,
                        outline=ACCENT + (255,), width=3)
    y = CAP_CY - th // 2
    for ln in lines:
        w = d.textlength(ln, font=font)
        d.text(((W - w) / 2, y), ln, font=font, fill=(255, 255, 255, 255))
        y += lh
    img.save(path)


def make_cta(text, path):
    """Aakhri 2 second ka on-screen text (peeli patti, kala text)."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    size = 68
    font = _font(size)
    lines = _wrap(d, text, font, W - 280)
    lh = int(size * 1.35)
    th = lh * len(lines)
    top = CAP_CY - th // 2 - 50
    d.rounded_rectangle([90, top, W - 90, top + th + 100], radius=50, fill=(255, 214, 74, 255))
    y = top + 50
    for ln in lines:
        w = d.textlength(ln, font=font)
        d.text(((W - w) / 2, y), ln, font=font, fill=(20, 20, 20, 255))
        y += lh
    img.save(path)


async def _edge(text, voice, path):
    """Awaaz banata hai aur har lafz ka waqt (word timing) bhi wapas deta hai."""
    import edge_tts
    kw = {}
    if TTS_RATE and TTS_RATE != "+0%":
        kw["rate"] = TTS_RATE
    try:
        comm = edge_tts.Communicate(text, voice, boundary="WordBoundary", **kw)
    except TypeError:
        try:
            comm = edge_tts.Communicate(text, voice, **kw)
        except TypeError:
            comm = edge_tts.Communicate(text, voice)
    words = []
    with open(path, "wb") as f:
        async for ch in comm.stream():
            if ch.get("type") == "audio":
                f.write(ch["data"])
            elif ch.get("type") == "WordBoundary":
                st = ch["offset"] / 1e7
                words.append((st, st + ch["duration"] / 1e7))
    return words


def make_audio(text, voice, path):
    """Returns word timings list [(start, end), ...]; khali ho to captions andaze se lagenge."""
    try:
        words = asyncio.run(_edge(text, voice, path))
        if os.path.getsize(path) < 1000:
            raise RuntimeError("empty audio")
        return words
    except Exception as e:
        print("edge-tts failed, using gTTS:", e)
        from gtts import gTTS
        gTTS(text, lang="en").save(path)
        return []


def duration(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path])
    return float(json.loads(out)["format"]["duration"])


def make_voice(segments, voice, out_dir):
    """Har jumle/tukre ki alag awaaz. Returns [{text, path, dur, words}, ...]"""
    os.makedirs(out_dir, exist_ok=True)
    res = []
    for i, text in enumerate(segments):
        p = f"{out_dir}/v{i}.mp3"
        words = make_audio(text, voice, p)
        res.append({"text": text, "path": p, "dur": duration(p), "words": words})
    return res


def _caption_spans(chunks, narration, words, speech, total):
    """Har caption kab dikhe: asli lafz-waqt mile to wo, warna harf-gintee se andaza."""
    counts = [max(1, len(c.split())) for c in chunks]
    n_words = len(narration.split())
    if words and len(words) == n_words and sum(counts) == n_words:
        starts, idx = [], 0
        for c in counts:
            starts.append(0.0 if idx == 0 else words[idx][0])
            idx += c
        starts.append(total)
        return [(starts[i], starts[i + 1]) for i in range(len(chunks))]
    weights = [len(c) + (10 if c.rstrip().endswith((".", "?", "!")) else 4 if c.rstrip().endswith(",") else 0)
               for c in chunks]
    tw = float(sum(weights)) or 1.0
    spans, t = [], 0.0
    for i, wgt in enumerate(weights):
        end = total if i == len(weights) - 1 else t + speech * wgt / tw
        spans.append((t, end))
        t = end
    return spans


def build(voices, tool_name, out_dir, max_seconds=60, recording=None, trim_start=0.0, starts=None):
    """voices: make_voice() ka result (intro, har step ka jumla, closing).
    starts: har voice kab shuru ho (record.py ke marks se); None ho to jumle ek ke baad ek.
    recording: record.py ki recording. trim_start: shuru ke kitne second kaatne hain.
    Video ki length MIN_SECONDS (45s) se max_seconds (60s) ke darmiyan rehti hai:
    chhoti ho to 45s tak barh jati hai, 60s se lambi ho to error.
    Aakhri CTA_SECS second mein on-screen CTA aata hai."""
    if not recording or not os.path.exists(recording):
        raise RuntimeError("screen recording nahi mili, video nahi banegi")
    if not voices:
        raise RuntimeError("awaaz nahi mili")
    os.makedirs(out_dir, exist_ok=True)
    bg = f"{out_dir}/bg.png"
    _gradient(BG_TOP, BG_BOTTOM).save(bg)

    # 1) har awaaz ka shuru-waqt (kabhi overlap nahi)
    st, prev_end = [], 0.0
    for i, vc in enumerate(voices):
        s = 0.0
        if i > 0:
            want = starts[i] if starts and i < len(starts) and starts[i] is not None else prev_end
            s = max(want, prev_end + 0.15)
        st.append(s)
        prev_end = s + vc["dur"]
    narr_end = prev_end
    total = narr_end + 0.3 + CTA_SECS
    if total > max_seconds:
        raise RuntimeError(f"video too long: {total:.0f}s (limit {max_seconds}s)")
    if total < MIN_SECONDS:
        print(f"video chhoti thi ({total:.1f}s), {MIN_SECONDS:.0f}s tak barhai")
        total = MIN_SECONDS
    print("voice starts:", [round(x, 1) for x in st], "| total: %.1fs" % total)

    # 2) captions (har awaaz ke andar lafz-waqt ke hisaab se)
    caps = []
    for i, vc in enumerate(voices):
        chunks = split_chunks(vc["text"])
        spans = _caption_spans(chunks, vc["text"], vc["words"], vc["dur"], vc["dur"])
        for c, (s, e) in zip(chunks, spans):
            caps.append((c, st[i] + s, st[i] + e))
    # har caption agle caption ke shuru tak (aakhri CTA ke shuru tak) dikhta rahe: beech mein khali nahi
    held = []
    for i, (c, s, e) in enumerate(caps):
        nxt = caps[i + 1][1] if i + 1 < len(caps) else total - CTA_SECS
        held.append((c, s, max(e, nxt)))
    caps = held
    for i, (c, s, e) in enumerate(caps):
        make_caption(c, tool_name, f"{out_dir}/c{i}.png")
    cta_png = f"{out_dir}/cta.png"
    make_cta(CTA_TEXT, cta_png)
    nc, ns = len(caps), len(voices)

    # 3) sab ko ek hi ffmpeg pass mein jorna
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-loop", "1", "-framerate", "30", "-t", f"{total:.2f}", "-i", bg]
    if trim_start > 0:
        cmd += ["-ss", f"{trim_start:.2f}"]
    cmd += ["-i", recording]
    for i in range(nc):
        cmd += ["-loop", "1", "-framerate", "30", "-t", f"{total:.2f}", "-i", f"{out_dir}/c{i}.png"]
    cmd += ["-loop", "1", "-framerate", "30", "-t", f"{total:.2f}", "-i", cta_png]
    for vc in voices:
        cmd += ["-i", vc["path"]]

    fc = (f"[1:v]setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration={total:.2f},fps=30,"
          f"scale={REC_MAX_W}:{REC_MAX_H}:force_original_aspect_ratio=decrease:flags=lanczos,format=yuv420p[rec];"
          f"[0:v][rec]overlay=(W-w)/2:{REC_Y}[v0];")
    for i, (c, s, e) in enumerate(caps):
        fc += f"[v{i}][{i + 2}:v]overlay=enable='between(t,{s:.2f},{e:.2f})'[v{i + 1}];"
    fc += (f"[v{nc}][{nc + 2}:v]overlay=enable='between(t,{total - CTA_SECS:.2f},{total:.2f})'[vout];")

    # audio: har tukra apni jagah tak silence se bhar kar ek ke baad ek jorna
    a0 = nc + 3
    for k in range(ns):
        if k < ns - 1:
            slot = st[k + 1] - st[k]
            fc += (f"[{a0 + k}:a]aresample=44100,aformat=channel_layouts=mono,"
                   f"apad=whole_dur={slot:.3f}[a{k}];")
        else:
            fc += f"[{a0 + k}:a]aresample=44100,aformat=channel_layouts=mono[a{k}];"
    fc += "".join(f"[a{k}]" for k in range(ns))
    # loudnorm: awaaz hamesha ek jaisi (mean -23..-16 dB ke andar) aur peak -2 dB se neeche (clipping nahi)
    fc += (f"concat=n={ns}:v=0:a=1,loudnorm=I=-17:TP=-2:LRA=7,aresample=44100,"
           f"aformat=channel_layouts=mono,apad=whole_dur={total:.2f}[aout]")

    final = f"{out_dir}/short.mp4"
    cmd += ["-filter_complex", fc, "-map", "[vout]", "-map", "[aout]",
            "-t", f"{total:.2f}",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", final]
    subprocess.run(cmd, check=True)
    return final, total
