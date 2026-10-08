import json, os, random

HERE = os.path.dirname(os.path.abspath(__file__))
FACTS = ("Free to use, no sign-up needed. Runs in your browser: text, files and images "
         "are not uploaded anywhere. Works on phones and tablets. Nothing to install.")


def _load():
    with open(os.path.join(HERE, "..", "tools.json"), encoding="utf-8") as f:
        return json.load(f)


def list_tools(base):
    return [{"url": "local:" + t["slug"], "slug": t["slug"], "name": t["name"]} for t in _load()]


def pick_tool(tools, history):
    used = {}
    for h in history:
        used[h.get("tool")] = used.get(h.get("tool"), 0) + 1
    least = min(used.get(t["slug"], 0) for t in tools)
    return random.choice([t for t in tools if used.get(t["slug"], 0) == least])


def page_info(url):
    slug = url.replace("local:", "")
    t = next(x for x in _load() if x["slug"] == slug)
    return {
        "title": t["name"] + " - free online tool",
        "description": t["description"],
        "text": (t["description"] + " Angle ideas (choose ONE that was not used recently): "
                 + " | ".join(t["angles"]) + ". Site facts: " + FACTS),
            }
