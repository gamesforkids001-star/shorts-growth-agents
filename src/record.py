"""record.py - tool page ki screen recording (Playwright).

Ab live site nahi khulti. Repo ke tools_local/<slug>.html se recording hoti hai.

record_demo(tool, demo, out_dir, ...) -> (recording_path, trim_start, marks)

v3:
- Recording ka size video ke tool-area se bilkul match (1080x1380): gradient/crop nahi.
- holds: har narrated step par awaaz ke jumle jitni der ruko (sync).
- marks: har step kab shuru hua (video.py awaaz ko usi waqt par lagata hai).
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
NARRATED = ("type", "click", "select", "upload", "highlight", "scroll_to")


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
    """tools_local/<slug>.html ka file:// address. Na mile to error."""
    f = Path(repo_root) / LOCAL_DIR / (_slug(tool) + ".html")
    f = f.resolve()
    if not f.exists():
        raise RecordError("local html nahi mili: %s/%s.html" % (LOCAL_DIR, _slug(tool)))
    return f.as_uri()


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
    if action not in ("wait", "type", "click", "select", "upload", "scroll",
                      "highlight", "scroll_to"):
        if "text" in step:
            action = "type"
        elif "file" in step:
            action = "upload"
        elif "ms" in step or "seconds" in step:
            action = "wait"
        elif "selector" in step:
            action = "click"
    return action


def narrated_indices(steps):
    """Un steps ke index jin par narration ka jumla bolega (agents.py, main.py yahi use karte hain)."""
    return [i for i, s in enumerate(steps) if _norm_step(s) in NARRATED]


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


def _run_step(page, step, repo_root):
    action = _norm_step(step)
    sel = step.get("selector")
    if action == "wait":
        ms = step.get("ms")
        if ms is None:
            ms = int(float(step.get("seconds", 1)) * 1000)
        page.wait_for_timeout(int(ms))
    elif action == "type":
        loc = _find(page, sel or "textarea")
        _smooth_center(loc)
        page.wait_for_timeout(500)
        loc.click()
        text = step.get("text") or step.get("value") or ""
        page.keyboard.type(text, delay=int(step.get("delay", 70)))
    elif action == "click":
        loc = _find(page, sel)
        _smooth_center(loc)
        page.wait_for_timeout(600)
        loc.click()
    elif action == "select":
        loc = _find(page, sel)
        val = step.get("value") or step.get("option")
        try:
            loc.select_option(val)
        except Exception:
            loc.select_option(label=val)
    elif action == "upload":
        loc = page.locator(sel or "input[type=file]").first
        f = step.get("file") or step.get("path")
        fp = Path(f)
        if not fp.is_absolute():
            fp = Path(repo_root) / f
        if not fp.exists():
            raise RecordError("upload file nahi mili: " + str(fp))
        loc.set_input_files(str(fp))
    elif action == "scroll":
        page.mouse.wheel(0, int(step.get("y", 400)))
    elif action == "scroll_to":
        # {"action": "scroll_to", "selector": "#kd-table"}
        loc = _find(page, sel)
        _smooth_center(loc)
        page.wait_for_timeout(int(step.get("hold_ms", 1200)))
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
        page.wait_for_timeout(int(step.get("hold_ms", 2500)))
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
    page.wait_for_timeout(int(step.get("after_ms", 500)))


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
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        ctx = browser.new_context(
            viewport={"width": VIEW_W, "height": VIEW_H},
            record_video_dir=str(vid_dir),
            record_video_size={"width": VIEW_W, "height": VIEW_H},
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
                _run_step(page, step, repo_root)
                hold = holds[i] if holds and i < len(holds) else None
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
