"""build_local.py - Blogger theme (XML) se har tool ka local page (tools_local/<slug>.html) banata hai.

Ye pages sirf screen recording ke liye hain (live website par koi visit nahi).
Maujood page kabhi overwrite nahi hota (force=True na ho to).

Theme file repo mein kahin bhi ho sakti hai: naam mein 'theme' aur '.xml' ho
(jaise easyfileonlinetools-theme-adsense-seo-final-1.xml).
"""
import re
from pathlib import Path

LOCAL_DIR = "tools_local"

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


def find_theme(repo_root):
    root = Path(repo_root)
    hits = []
    for pat in ("*theme*.xml", "theme/*.xml", "*/*theme*.xml", "*.xml"):
        hits += sorted(root.glob(pat))
        if hits:
            break
    for h in hits:
        try:
            if "window.TH=" in h.read_text(encoding="utf-8", errors="ignore"):
                return h
        except Exception:
            continue
    return None


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
    out = ["<!DOCTYPE html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">",
           "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
           "<title>%s</title>" % slug,
           "<style>%s</style>" % css,
           "<style>%s</style>" % FOCUS_CSS,
           "</head><body class=\"pt-static_page\">", body,
           "<script>window.__SLUG=%r;</script>" % slug,
           "<script>%s</script>" % core]
    for t in tools:
        out.append("<script>%s</script>" % t)
    out.append("<script>try{window.TH.boot();}catch(e){console.error(e);}</script>")
    out.append("</body></html>")
    return "\n".join(out)


def build_all(repo_root=".", only=None, force=False, log=print):
    """Missing pages banata hai. only = slug ki list ya None (sab). Returns bani hui slugs."""
    theme = find_theme(repo_root)
    if not theme:
        raise BuildError("theme XML file repo mein nahi mili (naam mein 'theme' aur .xml hona chahiye)")
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
        log("[build_local] bana diya: %s" % f)
    return made


if __name__ == "__main__":
    import sys
    made = build_all(sys.argv[1] if len(sys.argv) > 1 else ".")
    print("bane:", made)
