import asyncio, colorsys, json, os, random, re, subprocess
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


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


def find_shot(tool_name):
    slug = re.sub(r"[^a-z0-9]+", "-", tool_name.lower()).strip("-")
    shots_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shots")
    found = [p for p in (f"{shots_dir}/{slug}.png", f"{shots_dir}/{slug}-2.png") if os.path.exists(p)]
    return random.choice(found) if found else None


def make_background(shot, pal, flip, path):
    if shot and os.path.exists(shot):
        im = Image.open(shot).convert("RGB")
        w, h = im.size
        # phone ka status bar (oopar) aur navigation bar (neeche) hatao
        im = im.crop((0, int(h * 0.102), w, int(h * 0.944)))
        s = max(W / im.size[0], H / im.size[1])
        im = im.resize((int(im.size[0] * s) + 1, int(im.size[1] * s) + 1), Image.LANCZOS)
        l, t = (im.size[0] - W) // 2, (im.size[1] - H) // 2
        im = im.crop((l, t, l + W, t + H))
        im = Image.blend(im, Image.new("RGB", (W, H), (0, 0, 0)), 0.25)
    else:
        im = _gradient(*pal, flip=flip)
    im.save(path)


def make_caption(text, tool_name, pal, path):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f_small = _font(46)
    tw = d.textlength(tool_name, font=f_small)
    py = 140
    d.rounded_rectangle([(W - tw) / 2 - 40, py, (W + tw) / 2 + 40, py + 90], radius=45, fill=(255, 255, 255, 255))
    d.text(((W - tw) / 2, py + 15), tool_name, font=f_small, fill=pal[0] + (255,))
    size = 78
    font = _font(size)
    lines = _wrap(d, text, font, W - 200)
    while len(lines) > 5 and size > 50:
        size -= 6
        font = _font(size)
        lines = _wrap(d, text, font, W - 200)
    lh = int(size * 1.3)
    th = lh * len(lines)
    cy = 1350
    top = cy - th // 2 - 45
    d.rounded_rectangle([60, top, W - 60, top + th + 90], radius=40, fill=(0, 0, 0, 175))
    y = cy - th // 2
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


def build(scenes, tool_name, voice, out_dir, max_seconds=58, shot=None):
    os.makedirs(out_dir, exist_ok=True)
    pal = random_palette()
    flip = random.random() < 0.5
    if shot is None:
        shot = find_shot(tool_name)
    bg = f"{out_dir}/bg.png"
    make_background(shot, pal, flip, bg)

    wavs, durs = [], []
    for i, text in enumerate(scenes):
        mp3 = f"{out_dir}/s{i}.mp3"
        wav = f"{out_dir}/s{i}.wav"
        make_audio(text, voice, mp3)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp3,
                        "-af", "apad=pad_dur=0.35", "-ar", "44100", "-ac", "1", wav], check=True)
        wavs.append(wav)
        durs.append(duration(wav))
        make_caption(text, tool_name, pal, f"{out_dir}/c{i}.png")

    total = sum(durs)
    if total > max_seconds:
        raise RuntimeError(f"video too long: {total:.0f}s")

    lst = f"{out_dir}/list.txt"
    with open(lst, "w") as f:
        for w in wavs:
            f.write(f"file '{os.path.abspath(w)}'\n")
    voice_wav = f"{out_dir}/voice.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", lst, "-c", "copy", voice_wav], check=True)

    n = len(scenes)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", "30",
           "-t", f"{total:.2f}", "-i", bg]
    for i in range(n):
        cmd += ["-loop", "1", "-framerate", "30", "-t", f"{total:.2f}", "-i", f"{out_dir}/c{i}.png"]
    cmd += ["-i", voice_wav]

    fc = (f"[0:v]scale=w='trunc(1080*(1+0.10*t/{total:.2f})/2)*2':h=-2:eval=frame,"
          f"crop={W}:{H},format=yuv420p[v0];")
    start = 0.0
    for i in range(n):
        end = start + durs[i]
        fc += f"[v{i}][{i + 1}:v]overlay=enable='between(t,{start:.2f},{end:.2f})'[v{i + 1}];"
        start = end
    fc = fc.rstrip(";")

    final = f"{out_dir}/short.mp4"
    cmd += ["-filter_complex", fc, "-map", f"[v{n}]", "-map", f"{n + 1}:a",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", final]
    subprocess.run(cmd, check=True)
    return final, total
