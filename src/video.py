import asyncio, colorsys, json, os, random, subprocess
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# Layout: oopar tool ka naam, beech mein screen recording, neeche captions
REC_Y = 230          # recording kahan se shuru ho
REC_MAX_W = 960
REC_MAX_H = 1130
CAP_CY = 1620        # captions ka center


def random_palette():
    h = random.random()
    c1 = colorsys.hsv_to_rgb(h, random.uniform(0.5, 0.8), random.uniform(0.15, 0.3))
    c2 = colorsys.hsv_to_rgb((h + random.uniform(0.05, 0.2)) % 1, random.uniform(0.5, 0.8), random.uniform(0.4, 0.62))
    return tuple(int(x * 255) for x in c1), tuple(int(x * 255) for x in c2)


def _font(size):
    try:
        return ImageFont.truetype(FONT, size)
    except Exception:
        return ImageFont.load_default()


def _gradient(c1, c2, flip=False):
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    if flip:
        c1, c2 = c2, c1
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


def split_chunks(text, max_words=8):
    """Narration ko chhote caption tukron mein todta hai."""
    chunks, cur = [], []
    for w in text.split():
        cur.append(w)
        if len(cur) >= max_words or (w.endswith((".", "?", "!")) and len(cur) >= 3):
            chunks.append(" ".join(cur))
            cur = []
    if cur:
        chunks.append(" ".join(cur))
    return chunks


def make_caption(text, tool_name, pal, path):
    """Ek PNG: oopar tool ka naam, neeche caption."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f_small = _font(46)
    tw = d.textlength(tool_name, font=f_small)
    py = 90
    d.rounded_rectangle([(W - tw) / 2 - 40, py, (W + tw) / 2 + 40, py + 90], radius=45, fill=(255, 255, 255, 255))
    d.text(((W - tw) / 2, py + 15), tool_name, font=f_small, fill=pal[0] + (255,))
    size = 70
    font = _font(size)
    lines = _wrap(d, text, font, W - 200)
    while len(lines) > 3 and size > 48:
        size -= 6
        font = _font(size)
        lines = _wrap(d, text, font, W - 200)
    lh = int(size * 1.3)
    th = lh * len(lines)
    top = CAP_CY - th // 2 - 40
    d.rounded_rectangle([60, top, W - 60, top + th + 80], radius=40, fill=(0, 0, 0, 175))
    y = CAP_CY - th // 2
    for ln in lines:
        w = d.textlength(ln, font=font)
        d.text(((W - w) / 2, y), ln, font=font, fill=(255, 255, 255, 255))
        y += lh
    img.save(path)


async def _edge(text, voice, path):
    import edge_tts
    await edge_tts.Communicate(text, voice).save(path)


def make_audio(text, voice, path):
    try:
        asyncio.run(_edge(text, voice, path))
        if os.path.getsize(path) < 1000:
            raise RuntimeError("empty audio")
    except Exception as e:
        print("edge-tts failed, using gTTS:", e)
        from gtts import gTTS
        gTTS(text, lang="en").save(path)


def duration(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path])
    return float(json.loads(out)["format"]["duration"])


def build(narration, tool_name, voice, out_dir, max_seconds=58, recording=None, trim_start=0.0):
    """narration: poora voice-over text (ek string).
    recording: record.py ki banayi hui screen recording (webm/mp4).
    trim_start: recording ke shuru ke kitne second kaatne hain (page load wala hissa)."""
    if not recording or not os.path.exists(recording):
        raise RuntimeError("screen recording nahi mili, video nahi banegi")
    os.makedirs(out_dir, exist_ok=True)
    pal = random_palette()
    flip = random.random() < 0.5
    bg = f"{out_dir}/bg.png"
    _gradient(*pal, flip=flip).save(bg)

    # 1) ek hi voice-over
    mp3 = f"{out_dir}/voice.mp3"
    wav = f"{out_dir}/voice.wav"
    make_audio(narration, voice, mp3)
    speech = duration(mp3)
    tail = 0.6
    total = speech + tail
    if total > max_seconds:
        raise RuntimeError(f"video too long: {total:.0f}s")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp3,
                    "-af", f"apad=pad_dur={tail}", "-ar", "44100", "-ac", "1", wav], check=True)

    # 2) captions: words ke hisaab se waqt baant do
    chunks = split_chunks(narration)
    counts = [max(1, len(c.split())) for c in chunks]
    tot_words = sum(counts)
    spans, t = [], 0.0
    for i, c in enumerate(counts):
        end = total if i == len(counts) - 1 else t + speech * c / tot_words
        spans.append((t, end))
        t = end
        make_caption(chunks[i], tool_name, pal, f"{out_dir}/c{i}.png")

    # 3) sab ko ek hi ffmpeg pass mein jorna
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-loop", "1", "-framerate", "30", "-t", f"{total:.2f}", "-i", bg]
    if trim_start > 0:
        cmd += ["-ss", f"{trim_start:.2f}"]
    cmd += ["-i", recording]
    for i in range(len(chunks)):
        cmd += ["-loop", "1", "-framerate", "30", "-t", f"{total:.2f}", "-i", f"{out_dir}/c{i}.png"]
    cmd += ["-i", wav]

    fc = (f"[1:v]setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration={total:.2f},fps=30,"
          f"scale={REC_MAX_W}:{REC_MAX_H}:force_original_aspect_ratio=decrease,format=yuv420p[rec];"
          f"[0:v][rec]overlay=(W-w)/2:{REC_Y}[v0];")
    for i, (s, e) in enumerate(spans):
        fc += f"[v{i}][{i + 2}:v]overlay=enable='between(t,{s:.2f},{e:.2f})'[v{i + 1}];"
    fc = fc.rstrip(";")

    n = len(chunks)
    final = f"{out_dir}/short.mp4"
    cmd += ["-filter_complex", fc, "-map", f"[v{n}]", "-map", f"{n + 2}:a",
            "-t", f"{total:.2f}",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", final]
    subprocess.run(cmd, check=True)
    return final, total
