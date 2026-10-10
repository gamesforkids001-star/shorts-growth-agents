"""record.py - tool page ki screen recording (Playwright).

Ab live site nahi khulti. Repo ke tools_local/<slug>.html se recording hoti hai.

record_demo(tool, demo, out_dir, ...) -> (recording_path, trim_start, marks)

v6 (22 tools ke liye generic):
- tools_local/<slug>.html na ho to theme XML se build_local.py khud bana deta hai.
- type: pehle box khali karta hai (number/date/prefilled boxes mein bhi sahi chalta hai).
- set: range/color/date jaise inputs ki value set karta hai (input + change event ke saath).
- upload: ek se zyada file ("files": [...]) aur samples/ ki file na ho to khud bana leta hai.
- Narrated mode mein 'wait' max 0.4s, type/highlight/scroll_to/set awaaz ke jumle ke hisab se chalte hain.
- Jis click ke foran baad usi selector par type ho, us par alag narration nahi.
"""
import os
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

# video.py ke REC_W x REC_H se match (change mat karo)
VIEW_W, VIEW_H = 1080, 1380

# Tool ko bara karne ke liye zoom. Chota lage to 1.9, kata hua lage to 1.5.
ZOOM = float(os.environ.get("REC_ZOOM", "1.7"))

LOCAL_DIR = "tools_local"

# Jin steps par narration ka jumla bolta hai
NARRATED = ("type", "click", "select", "upload", "set", "highlight", "scroll_to")

# Narrated mode mein 'wait' ki hadd (second)
FAST_WAIT_MAX = 0.4


class BotCheckError(Exception):
    """Purana naam (main.py import kare to chal jaye). Ab use nahi hota."""


class RecordError(Exception):
    """Recording ke dauran koi masla."""


def _log(msg):
    print("[record] " + str(msg), flush=True)


def _slug(tool):
    s = tool.get("slug") or tool.get("name") or tool.get("title") or ""
    s = re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")
    if not s:
        raise RecordError("tool ka slug/name nahi mila")
    return s


def _local_url(tool, repo_root):
    """tools_local/<slug>.html ka file:// address. Page na ho to theme XML se khud bana leta hai."""
    slug = _slug(tool)
    f = (Path(repo_root) / LOCAL_DIR / (slug + ".html")).resolve()
    if not f.exists():
        try:
            try:
                from . import build_local
            except ImportError:
                import build_local
            build_local.build_all(repo_root, only=[slug], log=_log)
        except Exception as e:
            raise RecordError("local html nahi mili (%s/%s.html) aur bana bhi nahi saki: %s. "
                              "Theme XML file repo mein upload karo." % (LOCAL_DIR, slug, e))
        if not f.exists():
            raise RecordError("local html nahi mili: %s/%s.html" % (LOCAL_DIR, slug))
    return f.as_uri()


# ---------- sample files (upload wale tools ke liye) ----------

def _sample_font(size):
    from PIL import ImageFont
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
    except Exception:
        return ImageFont.load_default()


def _make_photo(w, h, seed):
    import random
    from PIL import Image, ImageDraw, ImageChops
    random.seed(seed)
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    c1 = (random.randint(20, 90), random.randint(80, 160), random.randint(150, 230))
    c2 = (random.randint(180, 255), random.randint(120, 200), random.randint(60, 140))
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)))
    d.ellipse([w * 0.62, h * 0.12, w * 0.86, h * 0.12 + w * 0.24], fill=(255, 236, 160))
    d.polygon([(0, h), (w * 0.35, h * 0.45), (w * 0.7, h)], fill=(40, 90, 70))
    d.polygon([(w * 0.4, h), (w * 0.75, h * 0.55), (w, h)], fill=(30, 70, 55))
    noise = Image.effect_noise((w, h), 40).convert("RGB")
    return Image.blend(img, ImageChops.add(img, noise, scale=2), 0.25)


def _make_pdf(fp, pages, title):
    from PIL import Image, ImageDraw
    imgs = []
    for n in range(1, pages + 1):
        im = Image.new("RGB", (794, 1123), "white")
        d = ImageDraw.Draw(im)
        d.rectangle([60, 60, 734, 140], fill=(37, 99, 235))
        d.text((90, 85), "%s - page %d" % (title, n), font=_sample_font(34), fill="white")
        for k in range(12):
            d.rectangle([90, 200 + k * 60, 704 - (k % 3) * 90, 222 + k * 60], fill=(210, 214, 220))
        imgs.append(im)
    imgs[0].save(str(fp), "PDF", save_all=True, append_images=imgs[1:], resolution=100.0)


def _ensure_sample(fp):
    """samples/ ki file na ho to bana do (repo mein upload karne ki zaroorat nahi)."""
    fp = Path(fp)
    if fp.exists():
        return
    fp.parent.mkdir(parents=True, exist_ok=True)
    suf = fp.suffix.lower()
    name = fp.stem.lower()
    if suf in (".jpg", ".jpeg"):
        _make_photo(1600, 1000, 1).save(str(fp), "JPEG", quality=95)
    elif suf == ".png":
        _make_photo(1000, 700, 2).save(str(fp), "PNG")
    elif suf == ".webp":
        _make_photo(1200, 800, 3).save(str(fp), "WEBP", quality=90)
    elif suf == ".pdf":
        _make_pdf(fp, 3 if name.endswith("a") else 2, "Sample document " + name[-1].upper())
    elif suf == ".txt":
        fp.write_text("Sample notes file.\nSecond line.\n", encoding="utf-8")
    else:
        raise RecordError("sample file banana nahi aata: " + str(fp))
    _log("sample file bana di: " + str(fp))


def _dump_elements(page):
    """Debug: selectors dhoondhne ke liye page ke controls print karo."""
    try:
        items = page.evaluate(
            """() => {
              const out = [];
              document.querySelectorAll(
                'textarea,input,button,select,[contenteditable="true"],[role="button"]'
              ).forEach(e => {
                const r = e.getBoundingClientRect();
                out.push({
                  tag: e.tagName.toLowerCase(),
                  id: e.id || '',
                  cls: (e.className && e.className.toString().slice(0, 60)) || '',
                  type: e.type || '',
                  ph: e.placeholder || '',
                  txt: (e.innerText || e.value || '').trim().slice(0, 30),
                  vis: r.width > 0 && r.height > 0
                });
              });
              return out;
            }"""
        )
        _log("---- PAGE CONTROLS (selectors yahan se lo) ----")
        for it in items:
            _log(str(it))
        _log("---- END CONTROLS ----")
    except Exception as e:
        _log("dump fail: " + str(e))


def _apply_zoom(page):
    """Page ko bara karo taake tool poori screen bhare (layout dobara set hota hai)."""
    if ZOOM and abs(ZOOM - 1.0) > 0.01:
        page.add_style_tag(content="html{zoom:%s !important;}" % ZOOM)
        page.wait_for_timeout(400)


def _norm_step(step):
    action = (step.get("action") or step.get("do") or step.get("op")
              or step.get("type") or "").lower()
    if action == "focus":
        action = "highlight"
    if action not in ("wait", "type", "click", "select", "upload", "set", "scroll",
                      "highlight", "scroll_to"):
        if "text" in step:
            action = "type"
        elif "file" in step or "files" in step:
            action = "upload"
        elif "ms" in step or "seconds" in step:
            action = "wait"
        elif "selector" in step:
            action = "click"
    return action


def narrated_indices(steps):
    """Un steps ke index jin par narration ka jumla bolega (agents.py, main.py yahi use karte hain).
    Jis click ke foran baad usi selector par type ho (sirf focus ke liye), us par jumla nahi."""
    out = []
    for i, s in enumerate(steps):
        a = _norm_step(s)
        if a not in NARRATED:
            continue
        if a == "click" and i + 1 < len(steps):
            nxt = steps[i + 1]
            if _norm_step(nxt) == "type" and nxt.get("selector") == s.get("selector"):
                continue
        out.append(i)
    return out


def _find(page, selector, timeout=8000):
    """Selector dhoondo; na mile to kuch aam fallback try karo."""
    candidates = [selector]
    if selector in ("textarea", "input", "input[type=text]"):
        candidates += ['textarea', '[contenteditable="true"]', 'input[type="text"]']
    for sel in candidates:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=timeout if sel == selector else 2500)
            return loc
        except Exception:
            continue
    _dump_elements(page)
    raise RecordError("selector nahi mila: " + str(selector))


def _smooth_center(loc):
    """Element ko screen ke beech mein smooth scroll karo."""
    try:
        loc.evaluate(
            "e => e.scrollIntoView({behavior: 'smooth', block: 'center'})"
        )
    except Exception:
        loc.scroll_into_view_if_needed()


def _run_step(page, step, repo_root, target=None, fast=False):
    """target: is step ko kitne second chalna chahiye (awaaz ke jumle ki length), ya None.
    fast: narrated mode (waits chhote)."""
    action = _norm_step(step)
    sel = step.get("selector")
    if action == "wait":
        ms = step.get("ms")
        if ms is None:
            ms = int(float(step.get("seconds", 1)) * 1000)
        ms = int(ms)
        if fast:
            ms = min(ms, int(FAST_WAIT_MAX * 1000))
        page.wait_for_timeout(ms)
    elif action == "type":
        loc = _find(page, sel or "textarea")
        _smooth_center(loc)
        page.wait_for_timeout(250 if fast else 500)
        loc.click()
        try:
            loc.fill("")  # pehle se bhari value hata do
        except Exception:
            pass
        text = step.get("text") or step.get("value") or ""
        delay = int(step.get("delay", 70))
        if target:
            # typing awaaz ke jumle ke andar khatam ho
            avail_ms = max(800, int(target * 1000) - 2000)
            delay = int(max(18, min(90, avail_ms / max(1, len(text)))))
        page.keyboard.type(text, delay=delay)
    elif action == "set":
        # range / color / date jaise inputs: {"do":"set","selector":"#pw-len","value":"24"}
        loc = _find(page, sel)
        _smooth_center(loc)
        page.wait_for_timeout(500)
        val = str(step.get("value", ""))
        loc.evaluate(
            """(e, v) => {
              e.value = v;
              e.dispatchEvent(new Event('input', {bubbles: true}));
              e.dispatchEvent(new Event('change', {bubbles: true}));
            }""",
            val,
        )
        if target:
            page.wait_for_timeout(max(500, int(target * 1000) - 1500))
    elif action == "click":
        loc = _find(page, sel)
        _smooth_center(loc)
        page.wait_for_timeout(250 if fast else 600)
        loc.click()
    elif action == "select":
        loc = _find(page, sel)
        _smooth_center(loc)
        page.wait_for_timeout(300)
        val = step.get("value") or step.get("option")
        try:
            loc.select_option(val)
        except Exception:
            loc.select_option(label=val)
    elif action == "upload":
        loc = page.locator(sel or "input[type=file]").first
        loc.wait_for(state="attached", timeout=8000)
        files = step.get("files")
        if not files:
            files = [step.get("file") or step.get("path")]
        paths = []
        for f in files:
            fp = Path(f)
            if not fp.is_absolute():
                fp = Path(repo_root) / f
            _ensure_sample(fp)
            if not fp.exists():
                raise RecordError("upload file nahi mili: " + str(fp))
            paths.append(str(fp))
        loc.set_input_files(paths)
    elif action == "scroll":
        page.mouse.wheel(0, int(step.get("y", 400)))
        if fast:
            page.wait_for_timeout(500)  # scroll nazar aaye
    elif action == "scroll_to":
        # {"action": "scroll_to", "selector": "#kd-table"}
        loc = _find(page, sel)
        _smooth_center(loc)
        hold = int(step.get("hold_ms", 1200))
        if target:
            hold = max(600, int(target * 1000) - 1200)
        page.wait_for_timeout(hold)
    elif action == "highlight":
        # {"action": "highlight", "selector": "#wc-stats", "hold_ms": 3000}
        loc = _find(page, sel)
        _smooth_center(loc)
        page.wait_for_timeout(700)
        try:
            loc.evaluate(
                """e => {
                  e.__old = [e.style.outline, e.style.outlineOffset,
                             e.style.borderRadius, e.style.transition];
                  e.style.transition = 'all .3s';
                  e.style.outline = '5px solid #ffd54a';
                  e.style.outlineOffset = '6px';
                  e.style.borderRadius = '12px';
                }"""
            )
        except Exception as ex:
            _log("highlight style fail: " + str(ex))
        hold = int(step.get("hold_ms", 2500))
        if target:
            # frame awaaz ke jumle tak dikhta rahe
            hold = max(700, int(target * 1000) - 1600)
        page.wait_for_timeout(hold)
        try:
            loc.evaluate(
                """e => {
                  const o = e.__old || ['', '', '', ''];
                  e.style.outline = o[0]; e.style.outlineOffset = o[1];
                  e.style.borderRadius = o[2]; e.style.transition = o[3];
                }"""
            )
        except Exception:
            pass
    else:
        raise RecordError("anjaan step: " + str(step))
    page.wait_for_timeout(int(step.get("after_ms", 250 if fast else 500)))


def record_demo(tool, demo, out_dir, max_seconds=55, repo_root=".", attempts=2,
                holds=None, intro_hold=0.0, closing_hold=0.0):
    """Returns (recording_path, trim_start, marks).

    holds: steps ki list ke barabar list; har narrated step ke liye kam az kam kitne second
           us step par rukna hai (awaaz ke jumle ki length). None = koi hold nahi.
    intro_hold: shuru mein itni der tool dikhao (hook + 'ye kya hai' wala jumla bolta hai).
    closing_hold: aakhri step ke baad itni der ruko (closing jumla).
    marks: {"steps": [har step ka shuru-waqt, trimmed video ke hisab se], "end": aakhri step khatam}
    """
    url = _local_url(tool, repo_root)  # local file, live site nahi
    steps = demo.get("steps", []) if isinstance(demo, dict) else (demo or [])
    if not steps:
        raise RecordError("is demo mein steps nahi hain")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    last = None
    for n in range(1, attempts + 1):
        try:
            return _record_once(url, steps, out_dir, max_seconds, repo_root,
                                holds, intro_hold, closing_hold)
        except Exception as e:
            last = e
            _log("attempt %d fail: %s" % (n, e))
    raise RecordError(str(last))


def _record_once(url, steps, out_dir, max_seconds, repo_root, holds, intro_hold, closing_hold):
    vid_dir = out_dir / ("rec_%d" % int(time.time()))
    vid_dir.mkdir(parents=True, exist_ok=True)
    marks = {"steps": [], "end": 0.0}
    fast = holds is not None
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        ctx = browser.new_context(
            viewport={"width": VIEW_W, "height": VIEW_H},
            record_video_dir=str(vid_dir),
            record_video_size={"width": VIEW_W, "height": VIEW_H},
            accept_downloads=True,
        )
        page = ctx.new_page()
        t0 = time.time()  # video yahin se shuru hoti hai
        trim_start = 0.0
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(600)
            _apply_zoom(page)
            page.wait_for_timeout(600)
            # loading wala hissa video se kaat do
            trim_start = max(0.0, time.time() - t0 - 0.3)
            base = t0 + trim_start  # trimmed video ka waqt 0 yahan hai

            if intro_hold and intro_hold > 0:
                page.wait_for_timeout(int(intro_hold * 1000))

            for i, step in enumerate(steps):
                if time.time() - base > max_seconds:
                    _log("max_seconds poore, steps rok diye")
                    break
                s0 = time.time()
                marks["steps"].append(round(s0 - base, 2))
                hold = holds[i] if holds and i < len(holds) else None
                _run_step(page, step, repo_root, target=hold, fast=fast)
                if hold:
                    left = hold - (time.time() - s0)
                    if left > 0:
                        page.wait_for_timeout(int(left * 1000))

            marks["end"] = round(time.time() - base, 2)
            if closing_hold and closing_hold > 0:
                page.wait_for_timeout(int(closing_hold * 1000))
            page.wait_for_timeout(800)
        finally:
            video = page.video
            ctx.close()  # video file yahan save hoti hai
            path = video.path() if video else None
            browser.close()
    if not path or not os.path.exists(path):
        raise RecordError("recording file nahi bani")
    _log("recording ok: %s (trim_start=%.2fs) marks=%s" % (path, trim_start, marks))
    return str(path), round(trim_start, 2), marks
