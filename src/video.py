import asyncio, colorsys, json, os, random, subprocess
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
def random_palette():
    """Har video ke liye naya dark->accent rang jodi (white text hamesha saaf dikhe)."""
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


def make_frame(text, tool_name, idx, total, pal, path, style=None):
    style = style or {}
    img = _gradient(*pal, flip=style.get("flip", False))
    d = ImageDraw.Draw(img)
    # tool name pill (top)
    f_small = _font(46)
    label = tool_name
    tw = d.textlength(label, font=f_small)
    py = style.get("pill_y", 230)
    d.rounded_rectangle([(W - tw) / 2 - 40, py, (W + tw) / 2 + 40, py + 90], radius=45, fill=(255, 255, 255))
    d.text(((W - tw) / 2, py + 15), label, font=f_small, fill=pal[0])
    # main caption
    size = 84
    font = _font(size)
    lines = _wrap(d, text, font, W - 160)
    while len(lines) > 7 and size > 52:
        size -= 6
        font = _font(size)
        lines = _wrap(d, text, font, W - 160)
    lh = int(size * 1.35)
    y = (H - lh * len(lines)) // 2
    for ln in lines:
        w = d.textlength(ln, font=font)
        d.text(((W - w) / 2 + 3, y + 3), ln, font=font, fill=(0, 0, 0))
        d.text(((W - w) / 2, y), ln, font=font, fill=(255, 255, 255))
        y += lh
    # progress dots
    gap = 40
    x0 = (W - gap * (total - 1)) / 2
    for i in range(total):
        r = 11 if i == idx else 7
        d.ellipse([x0 + gap * i - r, 1650 - r, x0 + gap * i + r, 1650 + r],
                  fill=(255, 255, 255) if i <= idx else (255, 255, 255, 90))
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


def build(scenes, tool_name, voice, out_dir, max_seconds=58):
    os.makedirs(out_dir, exist_ok=True)
    pal = random_palette()
    style = {"flip": random.random() < 0.5, "pill_y": random.choice([230, 230, 1420])}
    clips, total_dur = [], 0.0
    for i, text in enumerate(scenes):
        png = f"{out_dir}/s{i}.png"
        mp3 = f"{out_dir}/s{i}.mp3"
        mp4 = f"{out_dir}/s{i}.mp4"
        make_frame(text, tool_name, i, len(scenes), pal, png, style)
        make_audio(text, voice, mp3)
        dur = duration(mp3) + 0.4
        total_dur += dur
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", png, "-i", mp3,
            "-af", "apad=pad_dur=0.4", "-t", f"{dur:.2f}", "-r", "30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-ar", "44100", mp4,
        ], check=True)
        clips.append(mp4)
    if total_dur > max_seconds:
        raise RuntimeError(f"video too long: {total_dur:.0f}s")
    lst = f"{out_dir}/list.txt"
    with open(lst, "w") as f:
        for c in clips:
            f.write(f"file '{os.path.abspath(c)}'\n")
    final = f"{out_dir}/short.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", final,
    ], check=True)
    return final, total_dur
