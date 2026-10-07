import re
from .llm import ask_json

BANNED = [
    "guaranteed", "100%", "free money", "giveaway", "follow for follow", "f4f", "click here",
    "like and share", "tag a friend", "tag 3", "make money", "get rich", "you won't believe",
    "shocking", "hack", "cure", "miracle",
]
URL = re.compile(r"https?://|www\.", re.I)


def clean_tags(tags):
    out = []
    for t in tags or []:
        t = re.sub(r"[^A-Za-z0-9_]", "", str(t))
        if t and t.lower() != "shorts" and t not in out:
            out.append(t)
    return out


def hard_check(platform, m):
    """Rule-based checks (no AI). Returns list of problems."""
    issues = []
    text = " ".join(str(v) for k, v in m.items() if k not in ("tags", "hashtags")).lower()
    for w in BANNED:
        if w in text:
            issues.append(f"remove risky phrase: {w}")
    if URL.search(text):
        issues.append("do not write any URL")
    n = len(clean_tags(m.get("hashtags")))
    if not 3 <= n <= 5:
        issues.append("use 3 to 5 hashtags")
    if platform == "youtube":
        title = m.get("title", "")
        if not 10 <= len(title) <= 70:
            issues.append("title must be 10-70 characters")
        if title.isupper():
            issues.append("title must not be ALL CAPS")
        if not 60 <= len(m.get("description", "")) <= 600:
            issues.append("description must be 60-600 characters")
        if not 5 <= len(clean_tags(m.get("tags"))) <= 10:
            issues.append("use 5 to 10 tags")
    else:
        if not 20 <= len(m.get("caption", "")) <= 400:
            issues.append("caption must be 20-400 characters")
    return issues


def ai_check(platform, plan, m, policies):
    prompt = f"""You are a strict policy reviewer for {platform}.
Rules:
{policies['general']}
{policies[platform]}

Video script: {' '.join(plan['scenes'])}
Proposed text: {m}

Check: misleading or clickbait? unsupported claims? engagement bait? spammy or irrelevant tags?
Does the text honestly match the script? Return JSON only: {{"ok": true/false, "issues": ["..."]}}"""
    r = ask_json(prompt, "Be strict but fair. Only flag real problems.", 0.2)
    return [] if r.get("ok") else (r.get("issues") or ["policy problem"])


def review_script(plan, policies):
    prompt = f"""You are a strict policy reviewer for short videos on YouTube, Facebook and Instagram.
Rules:
{policies['general']}

Script scenes: {plan['scenes']}
Check: honest, no invented facts/stats, no superlatives, no medical/legal/financial/income claims,
no engagement bait, 5-7 scenes, each max 14 words.
Return JSON only: {{"ok": true/false, "issues": ["..."]}}"""
    r = ask_json(prompt, "Be strict but fair. Only flag real problems.", 0.2)
    ok = bool(r.get("ok"))
    scenes = plan.get("scenes") or []
    if not 4 <= len(scenes) <= 8 or any(len(s.split()) > 18 for s in scenes):
        ok = False
    return ok, r.get("issues", [])
