"""record.py - tool page ki screen recording (Playwright).

Ab live site nahi khulti. Repo ke tools_local/<slug>.html se recording hoti hai.

record_demo(tool, demo, out_dir, ...) -> (recording_path, trim_start, marks)

v7:
- AUTO ZOOM: har demo ko pehle bina video ke chala kar tool (#rt-ui) ki height naapi jati hai aur
  zoom 1.4-2.4 ke darmiyan khud chuna jata hai taake tool poori recording bhare. REC_ZOOM=1.7 jaisa
  number dene se fixed zoom, "auto" (default) se khud-ba-khud.
- THEME: video DARK theme mein (REC_THEME=dark default, "light" bhi chalta hai).
- Har run par page naye theme XML se dobara banta hai.

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

# Tool ko bara karne ke liye zoom. "auto" = har demo ke liye khud chuno. Number do to fixed.
_ZOOM_ENV = os.environ.get("REC_ZOOM", "auto").strip().lower()
ZOOM_MIN, ZOOM_MAX, ZOOM_STEP = 1.4, 2.4, 0.1
ZOOM_FALLBACK = 1.7
# Tool ke liye kitni height (px) milti hai (oopar/neeche thora margin chhor kar)
FILL_H = VIEW_H - 40
ZOOM = ZOOM_FALLBACK  # purana naam (agar koi aur file import kare)

# Video ka theme: "dark" (default) ya "light"
THEME = os.environ.get("REC_THEME", "dark").strip().lower()
if THEME not in ("dark", "light"):
    THEME = "dark"

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


_BUILT = set()  # is run mein jin slugs ke page naye XML se ban chuke


def _local_url(tool, repo_root):
    """tools_local/<slug>.html ka file:// address. Har run mein pehli baar page theme XML se dobara banta hai
    (taake purana hath se bana page bhi naye XML/theme se aa jaye)."""
    slug = _slug(tool)
    f = (Path(repo_root) / LOCAL_DIR / (slug + ".html")).resolve()
    key = (str(Path(repo_root).resolve()), slug, THEME)
    if key not in _BUILT:
        try:
            try:
                from . import build_local
            except ImportError:
                import build_local
            build_local.build_all(repo_root, only=[slug], force=True, log=_log)
            _BUILT.add(key)
        except Exception as e:
            if not f.exists():
                raise RecordError("local html nahi mili (%s/%s.html) aur bana bhi nahi saki: %s. "
                                  "Theme XML file repo mein upload karo." % (LOCAL_DIR, slug, e))
            _log("page dobara nahi bana (%s), purana page istemal ho raha hai" % e)
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


def _apply_theme(page):
    """html par data-theme set karo (dark/light)."""
    try:
        page.evaluate(
            """t => {
              document.documentElement.setAttribute('data-theme', t);
              try { localStorage.setItem('th', t); } catch (e) {}
            }""",
            THEME,
        )
    except Exception as e:
        _log("theme set fail: " + str(e))


def _apply_zoom(page, zoom, wait=400):
    """Page ko bara karo taake tool poori screen bhare (layout dobara set hota hai)."""
    if zoom and abs(zoom - 1.0) > 0.01:
        page.add_style_tag(content="html{zoom:%s !important;}" % zoom)
        if wait:
            page.wait_for_timeout(wait)


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


# ---------- auto zoom: tool ko poori recording par failana ----------

def _tool_height(page):
    """#rt-ui ki height (screen px, zoom ke baad)."""
    try:
        return float(page.evaluate(
            """() => {
              const e = document.getElementById('rt-ui');
              if (!e) return 0;
              return e.getBoundingClientRect().height;
            }"""))
    except Exception:
        return 0.0


def _run_step_dry(page, step, repo_root):
    """Naapne ke liye: step bina intezar ke chalao (video nahi banti)."""
    action = _norm_step(step)
    sel = step.get("selector")
    if action in ("wait", "highlight", "scroll_to", "scroll"):
        return
    if action == "type":
        loc = _find(page, sel or "textarea", timeout=4000)
        loc.click()
        try:
            loc.fill("")
        except Exception:
            pass
        page.keyboard.type(str(step.get("text") or step.get("value") or ""), delay=0)
    elif action == "set":
        loc = _find(page, sel, timeout=4000)
        loc.evaluate(
            """(e, v) => {
              e.value = v;
              e.dispatchEvent(new Event('input', {bubbles: true}));
              e.dispatchEvent(new Event('change', {bubbles: true}));
            }""",
            str(step.get("value", "")),
        )
    elif action == "click":
        _find(page, sel, timeout=4000).click()
    elif action == "select":
        loc = _find(page, sel, timeout=4000)
        val = step.get("value") or step.get("option")
        try:
            loc.select_option(val)
        except Exception:
            loc.select_option(label=val)
    elif action == "upload":
        loc = page.locator(sel or "input[type=file]").first
        loc.wait_for(state="attached", timeout=4000)
        files = step.get("files") or [step.get("file") or step.get("path")]
        paths = []
        for f in files:
            fp = Path(f)
            if not fp.is_absolute():
                fp = Path(repo_root) / f
            _ensure_sample(fp)
            paths.append(str(fp))
        loc.set_input_files(paths)
        page.wait_for_timeout(min(int(step.get("after_ms", 600)), 1500))
    page.wait_for_timeout(120)


def _probe_height(browser, url, steps, repo_root, zoom):
    """Is zoom par demo chala kar tool ki sab se bari height (px) lautao."""
    ctx = browser.new_context(viewport={"width": VIEW_W, "height": VIEW_H}, accept_downloads=True)
    try:
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(500)
        _apply_theme(page)
        _apply_zoom(page, zoom, wait=300)
        best = _tool_height(page)
        for step in steps:
            try:
                _run_step_dry(page, step, repo_root)
            except Exception as e:
                _log("zoom naap: step skip (%s)" % str(e).splitlines()[0][:80])
            best = max(best, _tool_height(page))
        return best
    finally:
        ctx.close()


def pick_zoom(url, steps, repo_root="."):
    """Is demo ke liye zoom chuno: sab se bara zoom (1.4-2.4) jis par tool poori recording ke andar aaye."""
    if _ZOOM_ENV != "auto":
        try:
            return float(_ZOOM_ENV)
        except ValueError:
            return ZOOM_FALLBACK
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox"])
            try:
                z = ZOOM_MAX
                while z >= ZOOM_MIN - 1e-6:
                    h = _probe_height(browser, url, steps, repo_root, round(z, 2))
                    _log("zoom naap: zoom %.1f -> tool height %.0fpx (hadd %dpx)" % (z, h, FILL_H))
                    if h <= 0:
                        return ZOOM_FALLBACK
                    if h <= FILL_H:
                        return round(z, 2)
                    z -= ZOOM_STEP
                _log("tool 1.4 zoom par bhi lamba hai, 1.4 istemal ho raha hai")
                return ZOOM_MIN
            finally:
                browser.close()
    except Exception as e:
        _log("zoom naapna fail (%s), %.1f istemal ho raha hai" % (e, ZOOM_FALLBACK))
        return ZOOM_FALLBACK


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
  
