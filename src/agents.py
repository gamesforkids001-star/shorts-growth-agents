import re
from .llm import ask_json
from .variety import FORMATS, HOOKS
from .record import narrated_indices, _norm_step

SYSTEM = (
    "You are a careful content team for a small free-tools website. "
    "Be honest, original and helpful. Never invent facts, features or statistics."
)

# Ye lafz/phrases kabhi use nahi karne (policy.py ki BANNED list ke mutabiq)
AVOID = (
    "instantly, guaranteed, 100%, free money, giveaway, follow for follow, click here, "
    "like and share, tag a friend, make money, get rich, you won't believe, shocking, "
    "hack, cure, miracle, number one, best ever"
)

# Narration me kisi bhi tarah ki call-to-action nahi honi chahiye
NO_CTA = (
    "check, visit, follow, subscribe, comment, share, link, profile, bio, description, "
    "go to, head to, try it, give it a try, download"
)

# Narration ki lambai: prompt mein 100-115 (policy.py ki 90-125 limit ke andar)
TARGET_MIN, TARGET_MAX, TARGET_AIM = 100, 115, 108


def _wc(text):
    return len(str(text).split())


def _resolve_demo(tool, demo):
    """demo dict ho to wahi, id (string) ho to tool ke demos mein se dhoondo."""
    if isinstance(demo, dict):
        return demo
    if isinstance(demo, str) and tool:
        for d in tool.get("demos") or []:
            if d.get("id") == demo:
                return d
    return {}


def _beat_texts(demo):
    """Har narrated step ka seedha bayan, usi tarteeb mein jis mein screen par hota hai."""
    steps = demo.get("steps", []) if demo else []
    out = []
    for i in narrated_indices(steps):
        s = steps[i]
        k = _norm_step(s)
        label = s.get("label") or ""
        if k == "type":
            t = str(s.get("text", "")).replace("\n", " / ")
            t = t if len(t) <= 60 else t[:57] + "..."
            out.append(f'the text "{t}" is typed into the {label or "tool"}')
        elif k == "click":
            out.append(f'the "{label or s.get("selector", "a control")}" control is pressed')
        elif k == "select":
            out.append(f'the "{label or "list"}" is set to "{s.get("value", "")}"')
        elif k == "set":
            out.append(f'the "{label or "setting"}" is changed to {s.get("value", "")}')
        elif k == "upload":
            n = len(s.get("files") or [1])
            what = label or "file"
            out.append(f'a small sample file is added ({what})' if n == 1
                       else f'{n} small sample files are added ({what})')
        elif k == "highlight":
            out.append(f'the "{label or "result"}" part of the tool is shown with a yellow frame')
        elif k == "scroll_to":
            out.append(f'the view moves down to the "{label or "next"}" part of the tool')
    return out


def _beat_labels(demo):
    """Har narrated step ka chhota naam (agar LLM kam jumle de to bharne ke kaam aata hai)."""
    steps = demo.get("steps", []) if demo else []
    out = []
    for i in narrated_indices(steps):
        s = steps[i]
        out.append(str(s.get("label") or "tool"))
    return out


def _clean_beats(plan, n):
    got = [" ".join(str(b).split()) for b in (plan.get("beats") or []) if str(b).strip()]
    if n and len(got) > n:  # zyada hon to aakhri mein jod do
        got = got[:n - 1] + [" ".join(got[n - 1:])]
    if not n:
        got = []
    return got


def _repeated_phrases(text, size=5):
    """Wo phrases (size lafz ke) jo narration mein 2 ya zyada baar aaye."""
    toks = re.findall(r"[a-z0-9']+", text.lower())
    first = {}
    found = []
    for i in range(len(toks) - size + 1):
        g = " ".join(toks[i:i + size])
        if g in first and i - first[g] >= size:
            if not any(g in f or f in g for f in found):
                found.append(g)
        else:
            first.setdefault(g, i)
    return found[:3]


def _local_problems(text):
    """Agents ke andar hi lambai aur repetition check (LLM ko wapas dikhane ke liye)."""
    probs = []
    w = _wc(text)
    if w < TARGET_MIN:
        probs.append(f"Total length is {w} words, too SHORT. It must be {TARGET_MIN}-{TARGET_MAX} words "
                     f"(aim for {TARGET_AIM}). Add about {TARGET_AIM - w} more words, spread over the "
                     "intro and the beat sentences, with NEW information about what each part does.")
    elif w > TARGET_MAX:
        probs.append(f"Total length is {w} words, too LONG. It must be {TARGET_MIN}-{TARGET_MAX} words "
                     f"(aim for {TARGET_AIM}). Remove about {w - TARGET_AIM} words.")
    for ph in _repeated_phrases(text):
        probs.append(f'The phrase "{ph}" is used more than once. Say each idea or feature list only ONCE '
                     "in the whole narration and use different words everywhere else.")
    return probs


def idea_and_script(tool, info, recent, policies, site_name, v, recent_openers, issues=None):
    demo = _resolve_demo(tool, v.get("demo"))
    beats = _beat_texts(demo)
    n = len(beats)
    if n:
        # intro (~24) + closing (~14) = ~38 words; baqi beats mein baanto, total ~108
        bw = max(8, min(24, round((TARGET_AIM - 38) / n)))
        beat_list = "\n".join(f"Beat {i + 1}: {b}" for i, b in enumerate(beats))
        beat_rule = (f'"beats": a list of EXACTLY {n} items, one for each beat above, in the same order. '
                     f"Each item is ONE sentence of about {bw} words and it is DIFFERENT from every other sentence. "
                     "While that beat happens on screen, the sentence says what is happening and what that "
                     "part of the tool is for.")
        intro_rule = ("\"intro\": 2 short sentences, about 24 words. Sentence 1 is the hook: a real everyday "
                      "problem this tool solves, as a question or a plain statement. Sentence 2 names the tool "
                      "and what it is for (tool description only). It is spoken while the tool is shown "
                      "before anything moves.")
    else:
        beat_list = "(no separate beats)"
        beat_rule = '"beats": an empty list [].'
        intro_rule = ("\"intro\": 6-7 short sentences, about 92 words in total, each sentence about a different "
                      "part of the tool. Sentence 1 is the hook: a real everyday problem this tool solves.")

    def make_prompt(extra):
        return f"""Write the voice-over for a 45 second vertical Short. The viewer sees a real screen
recording of this free browser tool being used, and hears your narration over it.
The narration is split into parts, and each part is spoken exactly while its beat is on screen.
Your job is to EXPLAIN the tool clearly.

Tool: {tool['name']}
Tool description (the ONLY source of facts): {info['text']}

Beats on screen, in order:
{beat_list}

Recent topics (do NOT repeat the angle or wording): {recent}

Policy rules you must follow:
{policies['general']}

Video format for THIS video: {FORMATS[v['format']]}
Opening style: {HOOKS[v['hook']]}
Recent opening lines used before (start differently, do not reuse their pattern): {recent_openers}
{extra}
Return these parts:
- {intro_rule}
- {beat_rule}
- "closing": 1 plain sentence, about 14 words, that only states what was shown.

Rules:
- Explain what each shown part DOES, in simple words, but never mention any feature that is not in
  the tool description or not shown on screen.
- NO REPETITION: every sentence must say something new. Mention the tool's list of features at most ONCE
  in the whole narration (only in the intro, in your own words). Never repeat a phrase, never copy long
  phrases from the tool description, and never restate the feature list in the beats or the closing.
- Do NOT say the word "button" and do not mention clicking, unless a click beat is listed above.
- Do not read out exact results, numbers or counts, because you cannot see them.
- No superlatives (best, #1, fastest), no stats.
- NEVER use any of these words or phrases: {AVOID}. Use plain words like "quickly" instead of "instantly".
- NO call to action of any kind. Never use these words or anything like them: {NO_CTA}.
  Never tell the viewer to do anything and never mention a profile, a link or a website address.
- Do not say or write any URL.
- The closing sentence must not ask or tell the viewer to do anything
  (example style: "That was the {tool['name']}, a free tool that runs in the browser.").
- Short sentences, easy to speak. LENGTH IS STRICT: intro + all beats + closing together must be
  {TARGET_MIN}-{TARGET_MAX} words (aim for {TARGET_AIM}). Count the words before answering.
  Never fewer than {TARGET_MIN} and never more than {TARGET_MAX}.

Return JSON only: {{"topic": "short topic label", "intro": "...", "beats": ["..."], "closing": "..."}}"""

    # pehle main.py/policy se aaye hue exact issues, phir har retry mein apne local issues
    carry = ""
    if issues:
        carry = ("\nYour PREVIOUS draft was rejected for these exact reasons. Fix every one of them:\n"
                 + "\n".join(f"- {i}" for i in issues) + "\n")

    plan = {}
    got = []
    local = ""
    for _ in range(3):
        plan = ask_json(make_prompt(carry + local), SYSTEM, 0.7)
        if not isinstance(plan, dict):
            plan = {}
        got = _clean_beats(plan, n)
        if len(got) != n:
            local = f"\nYou returned {len(got)} beats but EXACTLY {n} are required.\n"
            continue
        intro = " ".join(str(plan.get("intro", "")).split())
        closing = " ".join(str(plan.get("closing", "")).split())
        probs = _local_problems(" ".join([intro] + got + [closing]))
        if not probs:
            break
        local = ("\nYour last attempt was rejected for these exact reasons. Fix every one of them:\n"
                 + "\n".join(f"- {p}" for p in probs) + "\n")

    # kam hon to baqi steps ke liye chhota jumla bhar do (sync na tute)
    if n and len(got) < n:
        labels = _beat_labels(demo)
        for j in range(len(got), n):
            got.append(f"Here is the {labels[j] if j < len(labels) else 'tool'}.")
    intro = " ".join(str(plan.get("intro", "")).split())
    closing = " ".join(str(plan.get("closing", "")).split())
    segments = [intro] + got + [closing]
    segments = [s for s in segments if s]
    plan["segments"] = segments
    plan["n_beats"] = max(0, len(segments) - 2)
    plan["narration"] = " ".join(segments)
    plan["demo_id"] = (demo or {}).get("id", "")
    plan.setdefault("topic", f"{tool.get('name', 'tool')} walkthrough")
    return plan


# Safe fallback: koi LLM nahi, koi risky lafz nahi, koi CTA nahi, koi repetition nahi.
_CONNECT = ["First,", "Next,", "Then,", "After that,", "Now,", "Here,", "Finally,"]
_PAD = [
    "Each part of the page has one clear job.",
    "The steps are shown slowly so they are easy to follow.",
    "Watch the screen and you can follow every step as it happens.",
    "The recording shows the tool exactly as it looks on the page.",
    "Everything stays on one page, so nothing gets confusing.",
    "Take a moment to see how the page is laid out.",
    "The result appears in its own area of the page.",
    "Each step builds on the one before it.",
]


def fallback_script(tool, info, demo, v, policies):
    """Agar LLM script 3 retry ke baad bhi policy pass na kare, to ye safe script chalta hai."""
    demo = _resolve_demo(tool, demo)
    name = tool.get("name", "this tool")
    beats = _beat_texts(demo)
    n = len(beats)

    intro = f"Here is a quick look at how the {name} works."
    closing = f"That was the {name}, a free tool that runs in the browser."

    def build(texts):
        return [f"{_CONNECT[i % len(_CONNECT)]} {t}." for i, t in enumerate(texts)]

    segs = build(beats)
    total = _wc(intro) + _wc(closing) + sum(_wc(s) for s in segs)
    if n and total > 120:  # bahut lambi ho to steps ko chhota karo
        short = [f"the {lbl} part of the tool is shown" for lbl in _beat_labels(demo)]
        segs = build(short)

    middle = list(segs)
    used = 0
    while used < len(_PAD):
        total = _wc(intro) + _wc(closing) + sum(_wc(s) for s in middle)
        if total >= TARGET_MIN:
            break
        if n:
            middle[used % n] += " " + _PAD[used]
        else:
            intro += " " + _PAD[used]
        used += 1

    segments = [intro] + middle + [closing]
    return {
        "topic": f"{name} basic walkthrough",
        "segments": segments,
        "n_beats": n,
        "narration": " ".join(segments),
        "demo_id": (demo or {}).get("id", ""),
    }


def metadata(plan, tool, policies, recent_titles=(), info=None):
    desc = (info or {}).get("text", "") if isinstance(info, dict) else ""
    prompt = f"""Write separate, platform-specific text for the same short video.
Video topic: {plan['topic']}
Voice-over: {plan['narration']}
Tool: {tool['name']}
Tool description (the ONLY source of facts about the tool): {desc}
Recent titles (use a different title structure and different words): {list(recent_titles)}

General rules:
{policies['general']}

YouTube rules:
{policies['youtube']}

Facebook rules:
{policies['facebook']}

Instagram rules:
{policies['instagram']}

NEVER use any of these words or phrases anywhere: {AVOID}.
Do NOT claim anything about the tool that is not in the tool description above or in the voice-over
(for example: "no sign up", "no registration", "no download", "private", "works offline", "always free").

The three texts must be different in wording (not copy-paste), each in the style of its platform.
Hashtags: words only, without the # sign, no spaces.

Return JSON only:
{{"youtube": {{"title": "", "description": "", "tags": ["..."], "hashtags": ["..."]}},
  "facebook": {{"caption": "", "hashtags": ["..."]}},
  "instagram": {{"caption": "", "hashtags": ["..."]}}}}"""
    return ask_json(prompt, SYSTEM, 0.8)


def fix_metadata(platform, plan, current, issues, policies):
    prompt = f"""Fix this {platform} text so it fully follows the rules. Keep the same JSON keys.
Video topic: {plan['topic']}
Current text: {current}
Problems found: {issues}

Rules:
{policies['general']}
{policies[platform]}
NEVER use any of these words or phrases: {AVOID}.
Hashtags: words only, no # sign. Do not write URLs.

Return JSON only with the same keys as the current text."""
    return ask_json(prompt, SYSTEM, 0.5)
