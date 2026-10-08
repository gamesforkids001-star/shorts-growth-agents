import json, os, random

HERE = os.path.dirname(os.path.abspath(__file__))
FACTS = ("Free to use, no sign-up needed. Runs in your browser: text, files and images "
         "are not uploaded anywhere. Works on phones and tablets. Nothing to install.")


def _load():
    with open(os.path.join(HERE, "..", "tools.json"), encoding="utf-8") as f:
        return json.load(f)


def list_tools(base):
    """Har tool ke saath uska live page URL bhi deta hai (recording ke liye).
    Agar tools.json mein "url" likha ho to wahi use hota hai, warna base + /p/<slug>.html."""
    base = base.rstrip("/")
    out = []
    for t in _load():
        tool = dict(t)
        tool["url"] = t.get("url") or f"{base}/p/{t['slug']}.html"
        out.append(tool)
    return out


def pick_tool(tools, history):
    """Sab se kam use hua tool chunta hai, aur pichla tool dobara nahi (agar koi aur ho)."""
    used = {}
    for h in history:
        used[h.get("tool")] = used.get(h.get("tool"), 0) + 1
    least = min(used.get(t["slug"], 0) for t in tools)
    pool = [t for t in tools if used.get(t["slug"], 0) == least]
    last = history[-1].get("tool") if history else None
    pool = [t for t in pool if t["slug"] != last] or pool
    return random.choice(pool)


def page_info(tool):
    """Ab koi page scrape nahi hota. Sab kuch tools.json se aata hai.
    'tool' dict ho ya url/slug string, dono chalte hain."""
    if isinstance(tool, str):
        key = tool.replace("local:", "")
        tool = next((x for x in _load() if x["slug"] == key or x.get("url") == key), None)
        if tool is None:
            raise ValueError(f"tools.json mein ye tool nahi mila: {key}")
    return {
        "title": tool["name"] + " - free online tool",
        "description": tool["description"],
        "text": (tool["description"] + " Angle ideas (choose ONE that was not used recently): "
                 + " | ".join(tool.get("angles", [])) + ". Site facts: " + FACTS),
         }
