"""audit_tools.py - sab tools ke sab demos ka offline audit (internet/LLM/awaaz ki zaroorat nahi).

Chalane ka tareeqa (repo ke root se):
    python audit_tools.py                 -> sab 22 tools
    python audit_tools.py unit-converter  -> sirf ek tool
    python audit_tools.py --no-run        -> browser chalaye bina sirf JSON check

Har demo ke liye:
  1) tools_local/<slug>.html theme XML se banti hai
  2) demo ke SAB steps asli Chromium mein chalte hain (selector milta hai? upload ki sample file banti hai?)
  3) narrated beats ginte hain (1-2 = bahut kam, 7+ = bahut zyada)
  (angles ab pipeline mein LLM ko diye hi nahi jate, is liye unka audit nahi hota)
Result ek table + audit_report.json mein. Koi demo fail ho to exit code 1.
"""
import json
import os
import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src import record, site  # noqa: E402

def demo_text(tool, demo):
    parts = [tool.get("name", ""), demo.get("title", "")]
    for s in demo.get("steps", []):
        for k in ("label", "text", "value", "selector", "files", "file"):
            if k in s:
                parts.append(json.dumps(s[k]) if not isinstance(s[k], str) else s[k])
    return " ".join(parts)


def run_demo(browser, tool, demo):
    """Demo ke sab steps chalata hai. Returns (ok, seconds, error)."""
    url = record._local_url(tool, str(ROOT))
    ctx = browser.new_context(viewport={"width": record.VIEW_W, "height": record.VIEW_H},
                              color_scheme="dark", accept_downloads=True)
    ctx.add_init_script(record.CURSOR_JS)
    # Sirf internet na hone par: PDF_LIB_LOCAL=/path/pdf-lib.min.js se cdnjs wali pdf-lib local file se chalti hai
    local_lib = os.environ.get("PDF_LIB_LOCAL")
    if local_lib and os.path.exists(local_lib):
        ctx.route("**/pdf-lib*.js", lambda r: r.fulfill(path=local_lib, content_type="application/javascript"))
    page = ctx.new_page()
    t0 = time.time()
    err = ""
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(400)
        record._apply_zoom(page)
        for i, step in enumerate(demo.get("steps", [])):
            try:
                record._run_step(page, step, str(ROOT), target=None, fast=True)
            except Exception as e:
                err = "step %d (%s %s): %s" % (i + 1, record._norm_step(step), step.get("selector", ""),
                                               str(e).splitlines()[0][:120])
                break
    except Exception as e:
        err = "page: " + str(e).splitlines()[0][:150]
    finally:
        secs = time.time() - t0
        ctx.close()
    return (not err), secs, err


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    no_run = "--no-run" in sys.argv
    tools = site.load_all()
    if args:
        tools = [t for t in tools if t["slug"] in args]
        if not tools:
            print("aisa tool nahi mila:", args)
            return 2

    rows, fails = [], 0
    pw = browser = None
    if not no_run:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        browser = pw.chromium.launch(args=["--no-sandbox"])
    try:
        for t in tools:
            demos = t.get("demos") or []
            if not demos:
                rows.append((t["slug"], "-", "-", "-", "FAIL: koi demo nahi"))
                fails += 1
                continue
            for d in demos:
                n = len(record.narrated_indices(d.get("steps", [])))
                note = []
                if n <= 2:
                    note.append("beats kam (%d): beat lambe honge" % n)
                if n >= 7:
                    note.append("beats zyada (%d)" % n)
                if no_run:
                    status = "skip-run"
                else:
                    ok, secs, err = run_demo(browser, t, d)
                    status = ("ok %.0fs" % secs) if ok else ("FAIL " + err)
                    if not ok:
                        fails += 1
                rows.append((t["slug"], d.get("id", "?"), n, status, "; ".join(note)))
    finally:
        if browser:
            browser.close()
        if pw:
            pw.stop()

    print("\n%-24s %-20s %-5s %-34s %s" % ("tool", "demo", "beats", "browser run", "note"))
    print("-" * 110)
    for r in rows:
        print("%-24s %-20s %-5s %-34s %s" % (r[0], r[1], r[2], str(r[3])[:34], r[4]))
    (ROOT / "audit_report.json").write_text(json.dumps(
        {"rows": [list(map(str, r)) for r in rows]}, indent=1, ensure_ascii=False))
    print("\nFAILS: %d (audit_report.json mein poori report)" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
