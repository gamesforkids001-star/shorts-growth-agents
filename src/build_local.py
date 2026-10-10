"""build_local.py - Blogger theme (XML) se har tool ka local page (tools_local/<slug>.html) banata hai.

Ye pages sirf screen recording ke liye hain (live website par koi visit nahi).
v7:
- Theme XML: repo mein agar kai XML hon to sahi wali chunti hai (window.TH= wali; Easyfileonlinetools.xml
  ko tarjeeh, phir sab se bari, phir sab se nayi).
- Har run par pages dobara bante hain (force=True default), taake purana hath se bana page bhi naye XML se aa jaye.
- REC_THEME (default "dark", "light" bhi chalta hai): page ka data-theme set karta hai.
"""
import os
import re
from pathlib import Path

LOCAL_DIR = "tools_local"

# Video DARK theme mein (live site phone par dark dikhti hai). "light" bhi chalta hai.
THEME = os.environ.get("REC_THEME", "dark").strip().lower()
if THEME not in ("dark", "light"):
    THEME = "dark"

SKIP_DIRS = {".git", "node_modules", LOCAL_DIR, "output", "outputs", "samples", "__pycache__"}

# Recording ke liye sirf tool dikhao: header, breadcrumb, article, sidebar, ads, footer chhupao
FOCUS_CSS = """
.skip,.site-header,#site-header,#rt-crumb,#rt-article,.side,aside,.ad-slot,.site-footer,#site-footer,
#cookie-banner,.cookie,#view-home,#blog-wrap,#rt-head{display:none !important;}
body{margin:0;background:var(--bg,#F8FAFC);}
#content{padding:18px 0 40px;}
.tool-layout{display:block !important;}
.tool-main{max-width:100% !important;width:100% !important;}
.tool-box{margin:0 auto;}
"""


class BuildError(Exception):
    pass


def find_theme(repo_root, log=print):
    """Repo ke sab .xml files dekho; jin mein 'window.TH=' ho unmein se behtareen chuno.
    Tarteeb: (1) naam Easyfileonlinetools.xml, (2) sab se bari file, (3) sab se nayi file."""
    root = Path(repo_root)
    cands = []
    for p in root.rglob("*.xml"):
        if any(part in SKIP_DIRS or part.startswith(".") for part in p.relative_to(root).parts[:-1]):
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if "window.TH=" not in txt:
            continue
        pref = 1 if p.name.lower() == "easyfileonlinetools.xml" else 0
        cands.append((pref, len(txt), p.stat().st_mtime, p))
    if not cands:
        return None
    cands.sort(key=lambda c: (c[0], c[1], c[2]), reverse=True)
    best = cands[0][3]
    if len(cands) > 1:
        log("[build_local] %d theme XML mili, istemal: %s" % (len(cands), best))
    return best


def _parts(xml):
    m = re.search(r"<b:skin><!\[CDATA\[(.*?)\]\]></b:skin>", xml, re.S)
    if not m:
        raise BuildError("theme mein CSS (b:skin) nahi mili")
    css = re.sub(r"<(?:Group|Variable|/Group)[^>]*>", "", m.group(1))
    scripts = []
    for s in re.findall(r"<script>(.*?)</script>", xml, re.S):
        s = s.replace("//<![CDATA[", "").replace("//]]>", "")
        scripts.append(s)
    core = [s for s in scripts if "window.TH=(function" in s]
    tools = [s for s in scripts if ("TH.add(" in s or "TH.addPage(" in s) and "window.TH=(function" not in s]
    if not core or not tools:
        raise BuildError("theme mein core/tool scripts nahi mile")
    return css, core[0], tools


def tool_slugs(xml):
    return re.findall(r"\n slug:'([^']+)',name:", xml)


def _page(slug, css, core, tools):
    core = core.replace("function routeFromLocation(){",
                        "function routeFromLocation(){return window.__SLUG;", 1)
    if "window.__SLUG;" not in core:
        raise BuildError("theme ka router patch nahi hua")
    body = """
<div hidden id="pgdata" data-type="static_page" data-home="https://easyfileonlinetools.blogspot.com/" data-title="Easy File Online Tools" data-desc="Free online tools"></div>
<main id="content" tabindex="-1">
  <div id="view-home"></div>
  <div id="view-route"><div class="container">
    <nav id="rt-crumb"></nav>
    <div class="tool-layout"><div class="tool-main">
      <div id="rt-head"></div>
      <div class="tool-box" id="rt-ui"></div>
      <article class="article" id="rt-article"></article>
    </div>
    <aside class="side"><div class="side-box" id="rt-related"></div></aside></div>
  </div></div>
  <div class="container blog-wrap" id="blog-wrap"></div>
</main>
<div class="toast" id="toast" role="status"></div>
"""
    out = ["<!DOCTYPE html>\n<html lang=\"en\" data-theme=\"%s\"><head><meta charset=\"utf-8\">" % THEME,
           "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
           "<title>%s</title>" % slug,
           "<style>%s</style>" % css,
           "<style>%s</style>" % FOCUS_CSS,
           "</head><body class=\"pt-static_page\">", body,
           "<script>window.__SLUG=%r;try{localStorage.setItem('th','%s');}catch(e){}</script>" % (slug, THEME),
           "<script>%s</script>" % core]
    for t in tools:
        out.append("<script>%s</script>" % t)
    out.append("<script>try{window.TH.boot();}catch(e){console.error(e);}</script>")
    out.append("</body></html>")
    return "\n".join(out)


def build_all(repo_root=".", only=None, force=True, log=print):
    """Pages banata hai (har baar dobara, force=True). only = slug ki list ya None (sab). Returns bani hui slugs."""
    theme = find_theme(repo_root, log=log)
    if not theme:
        raise BuildError("theme XML file repo mein nahi mili (aisi .xml chahiye jis mein 'window.TH=' ho)")
    xml = theme.read_text(encoding="utf-8")
    css, core, tools = _parts(xml)
    slugs = [s for s in tool_slugs(xml)]
    out_dir = Path(repo_root) / LOCAL_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    made = []
    for slug in slugs:
        if only and slug not in only:
            continue
        f = out_dir / (slug + ".html")
        if f.exists() and not force:
            continue
        f.write_text(_page(slug, css, core, tools), encoding="utf-8")
        made.append(slug)
        log("[build_local] bana diya: %s (theme=%s, xml=%s)" % (f, THEME, theme.name))
    return made


if __name__ == "__main__":
    import sys
    made = build_all(sys.argv[1] if len(sys.argv) > 1 else ".")
    print("bane:", made)
