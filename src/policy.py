import re
from .llm import ask_json

BANNED = [
    "guaranteed", "100%", "free money", "giveaway", "follow for follow", "f4f", "click here",
    "like and share", "tag a friend", "tag 3", "make money", "get rich", "you won't believe",
    "shocking", "hack", "cure", "miracle", "number one", "no. 1", "best ever", "instantly",
]
URL = re.compile(r"https?://|www\.", re.I)

# 30-40 second video ke liye narration ki lambai (words mein)
MIN_WORDS, MAX_WORDS = 45, 95


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

Video narration (this is what the viewer hears while a real screen recording of the tool plays):
{plan['narration']}

Proposed text: {m}

Check: misleading or clickbait? unsupported claims? engagement bait? spammy or irrelevant tags?
Does the text honestly match the narration and the screen recording? Return JSON only: {{"ok": true/false, "issues": ["..."]}}"""
    r = ask_json(prompt, "Be strict but fair. Only flag real problems.", 0.2)
    return [] if r.get("ok") else (r.get("issues") or ["policy problem"])


def too_similar(plan, openers):
    """Pichli videos ke shuru jaisa hi shuru ho to repeat maana jayega."""
    words = (plan.get("narration") or "").lower().split()
    start = " ".join(words[:6])
    for o in openers or []:
        if o and " ".join(str(o).lower().split()[:6]) == start:
            return True
    return False


def review_script(plan, policies, tool=None, demo=None, openers=None):
    """Narration ko check karta hai. Returns (ok, issues)."""
    text = (plan.get("narration") or "").strip()
    issues = []
    words = len(text.split())

    if not MIN_WORDS <= words <= MAX_WORDS:
        issues.append(f"narration must be {MIN_WORDS}-{MAX_WORDS} words (now {words})")
    low = text.lower()
    for w in BANNED:
        if w in low:
            issues.append(f"remove risky phrase: {w}")
    if URL.search(text):
        issues.append("do not say or write any URL")
    if "link in my profile" not in low and "profile" not in low:
        issues.append("end with a mention that the link is in my profile")
    if too_similar(plan, openers):
        issues.append("opening is too similar to a recent video, change it")
    if issues:
        return False, issues

    facts = ""
    if tool:
        facts = f"Tool: {tool.get('name')} - {tool.get('description')}\n"
    if demo:
        facts += f"What is shown on screen: {demo.get('title', '')} | steps: {demo.get('steps', '')}\n"

    prompt = f"""You are a strict policy reviewer for short videos on YouTube, Facebook and Instagram.
Rules:
{policies['general']}

Known facts about the tool and the screen recording:
{facts}
Narration: {text}

Check: honest, no invented facts/stats, no superlatives, no medical/legal/financial/income claims,
no engagement bait, no claim about privacy/security/speed unless it is in the known facts,
and the narration only describes things that are actually shown on screen.
Return JSON only: {{"ok": true/false, "issues": ["..."]}}"""
    r = ask_json(prompt, "Be strict but fair. Only flag real problems.", 0.2)
    return bool(r.get("ok")), r.get("issues", [])
