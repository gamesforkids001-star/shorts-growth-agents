import re, html, random, requests

SKIP = ("privacy", "about", "contact", "terms", "disclaimer", "cookie", "sitemap", "search")
UA = {"User-Agent": "Mozilla/5.0"}


def list_tools(base):
    urls = set()
    for sm in ("sitemap.xml", "sitemap-pages.xml"):
        try:
            t = requests.get(f"{base}/{sm}", timeout=30, headers=UA).text
            urls.update(re.findall(r"<loc>\s*(.*?)\s*</loc>", t))
        except Exception as e:
            print("sitemap error", sm, e)
    tools = []
    for u in sorted(urls):
        if not u.endswith(".html"):
            continue
        slug = u.rsplit("/", 1)[-1][:-5]
        if any(s in slug for s in SKIP):
            continue
        tools.append({"url": u, "slug": slug, "name": slug.replace("-", " ").title()})
    return tools


def pick_tool(tools, history):
    used = {}
    for h in history:
        used[h.get("tool")] = used.get(h.get("tool"), 0) + 1
    least = min(used.get(t["slug"], 0) for t in tools)
    return random.choice([t for t in tools if used.get(t["slug"], 0) == least])


def page_info(url):
    t = requests.get(url, timeout=30, headers=UA).text
    title = re.search(r"<title>(.*?)</title>", t, re.S)
    desc = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', t, re.S)
    body = re.sub(r"<(script|style)[\s\S]*?</\1>", " ", t)
    body = re.sub(r"<[^>]+>", " ", body)
    body = html.unescape(re.sub(r"\s+", " ", body)).strip()
    return {
        "title": html.unescape(title.group(1).strip()) if title else "",
        "description": html.unescape(desc.group(1).strip()) if desc else "",
        "text": body[:1500],
    }
