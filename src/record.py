"""record.py - tool page ki screen recording (Playwright).

Ab live site nahi khulti. Repo ke tools_local/<slug>.html se recording hoti hai.

record_demo(tool, demo, out_dir) -> (recording_path, trim_start)
"""
import os
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

VIEW_W, VIEW_H = 960, 1130  # video.py ke recording area se match

LOCAL_DIR = "tools_local"


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


def _norm_step(step):
    action = (step.get("action") or step.get("do") or step.get("op")
              or step.get("type") or "").lower()
    if action not in ("wait", "type", "click", "select", "upload", "scroll"):
        if "text" in step:
            action = "type"
        elif "file" in step:
            action = "upload"
        elif "ms" in step or "seconds" in step:
            action = "wait"
        elif "selector" in step:
            action = "click"
    return action


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
        loc.scroll_into_view_if_needed()
        loc.click()
        text = step.get("text") or step.get("value") or ""
        page.keyboard.type(text, delay=int(step.get("delay", 45)))
    elif action == "click":
        loc = _find(page, sel)
        loc.scroll_into_view_if_needed()
        page.wait_for_timeout(400)
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
    else:
        raise RecordError("anjaan step: " + str(step))
    page.wait_for_timeout(int(step.get("after_ms", 500)))


def record_demo(tool, demo, out_dir, max_seconds=55, repo_root=".", attempts=2):
    """Returns (recording_path, trim_start)."""
    url = _local_url(tool, repo_root)  # local file, live site nahi
    steps = demo.get("steps", []) if isinstance(demo, dict) else (demo or [])
    if not steps:
        raise RecordError("is demo mein steps nahi hain")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    last = None
    for n in range(1, attempts + 1):
        try:
            return _record_once(url, steps, out_dir, max_seconds, repo_root)
        except Exception as e:
            last = e
            _log("attempt %d fail: %s" % (n, e))
    raise RecordError(str(last))


def _record_once(url, steps, out_dir, max_seconds, repo_root):
    vid_dir = out_dir / ("rec_%d" % int(time.time()))
    vid_dir.mkdir(parents=True, exist_ok=True)
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
            page.wait_for_timeout(1000)
            # loading wala hissa video se kaat do
            trim_start = max(0.0, time.time() - t0 - 0.3)
            for step in steps:
                if time.time() - t0 - trim_start > max_seconds:
                    _log("max_seconds poore, steps rok diye")
                    break
                _run_step(page, step, repo_root)
            page.wait_for_timeout(1500)
        finally:
            video = page.video
            ctx.close()  # video file yahan save hoti hai
            path = video.path() if video else None
            browser.close()
    if not path or not os.path.exists(path):
        raise RecordError("recording file nahi bani")
    _log("recording ok: %s (trim_start=%.1fs)" % (path, trim_start))
    return str(path), round(trim_start, 1)
