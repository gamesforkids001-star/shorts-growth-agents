"""agents.py v11 - narration + metadata (sab 22 tools ke liye generic).

v11: fallback_script naye sire se: koi generic filler (_PAD) nahi. Har jumla demo ke asal step se banta hai
(step + screen par kya dikhta hai + recap). Upload beat ab 'you add a file in the <label> area'.

v10: vague lafz (parameters, density...) mana, doosre tool ke tags filter, 'This video shows' mana.

v9 badlav:
- Angles ab LLM ko nahi diye jate (pehle info['text'] mein 'Angle ideas' jati thi, isi se video mein
  aisi baat aa jati thi jo screen par nahi thi, jaise unit converter mein 'weight').
- LLM ko saaf bataya jata hai ke video SIRF kya dikhata hai (demo title + beats); description mein jo
  features zyada hain unka naam nahi lena.
- Intro chhota (10-18 words) taake pehle 5-6 second mein hi action shuru ho.
- Closing ab LLM nahi likhta: safe jumla code se banta hai (ghalat fel 'measure' jaisi ghalti nahi).
- Speed/time/frequency claims (quickly, right away, every day, a lot of time...) mana (policy.BANNED).
- Fallback script mein meta lafz (recording, quick look, follow every step) nahi.
- Metadata: title/description/hashtags sirf us cheez se jure jo video mein dikhi.
"""
import re
from .llm import ask_json
from .variety import FORMATS, HOOKS
from .record import narrated_indices, _norm_step
from . import policy

SYSTEM = (
    "You are a careful content team for a small free-tools website. "
    "Be honest, original and helpful. Never invent facts, features or statistics."
)

# Ye lafz/phrases kabhi use nahi karne: policy.BANNED se seedha liya jata hai (dono hamesha barabar rahen)
AVOID = ", ".join(policy.BANNED)

# vague / technical-sounding lafz jo narration ko ghalat ya samajh se bahar bana dete hain
ABSTRACT = ["parameter", "parameters", "density", "visual item", "visual outcome", "data volume",
            "actively", "utilize", "leverage", "seamless", "robust", "streamline", "workflow"]
ABSTRACT_TXT = ", ".join(ABSTRACT)

# doosre tools ke kaam: tag/hashtag mein tabhi jo video mein dikhe
TASK_WORDS = ["resize", "resizing", "crop", "convert", "merge", "split", "rotate", "compress", "edit", "watermark"]
GENERIC_TAGS = {"tools", "tool", "free", "online", "viral", "trending", "fyp", "math", "photo", "browser"}

# Narration me kisi bhi tarah ki call-to-action nahi honi chahiye
NO_CTA = (
    "check, visit, follow, subscribe, comment, share, link, profile, bio, description, "
    "go to, head to, try it, give it a try, download"
)

# Narration ki lambai (words). Policy 100-125 maangti hai; yahan 104-118 (policy ke andar).
# Awaaz ~2.5 words/second: 104-118 words = ~42-47s bolna + gaps + 2s CTA = 46-52s video.
TARGET_MIN, TARGET_MAX, TARGET_AIM = 104, 118, 110

# Intro: sirf 2 chhote jumle (hook + tool ka naam), taake pehle 5-6 second mein action shuru ho.
INTRO_MIN, INTRO_MAX = 10, 18

# Closing code se banti hai (LLM nahi likhta). Har jumla sirf wahi kehta hai jo hamesha sach hai.
CLOSINGS = [
    "That was the {name}, a free tool that runs in the browser.",
    "And that is the {name}, a free browser tool.",
    "That is how the {name} works, free and in the browser.",
    "This was the {name}, a free tool for the browser.",
]


def _wc(text):
    return len(str(text).split())


def make_closing(tool, demo):
    """Tool + demo ke hisaab se tay (random nahi) closing jumla."""
    key = str((tool or {}).get("slug") or (tool or {}).get("name") or "") + str((demo or {}).get("id", ""))
    i = sum(ord(c) for c in key) % len(CLOSINGS)
    return CLOSINGS[i].format(name=(tool or {}).get("name", "this tool"))


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
            raw = str(s.get("text", ""))
            if "\n" in raw.strip():
                out.append(f'you type several lines of text into the {label or "box"}')
            elif len(raw) <= 12:
                out.append(f'you type "{raw}" into the {label or "box"}')
            else:  # lamba sample text quote nahi karte (uske lafz policy/claims se takra sakte hain)
                out.append(f'you type some sample text into the {label or "box"}')
        elif k == "click":
            out.append(f'you tap the {label or "button"}')
        elif k == "select":
            out.append(f'you choose {s.get("value", "")} for the {label or "option"}')
        elif k == "set":
            out.append(f'you set the {label or "option"} to {s.get("value", "")}')
        elif k == "upload":
            n = len(s.get("files") or [1])
            what = label or "file"
            out.append(f'you add a file in the {what} area' if n == 1
                       else f'you add {n} files in the {what} area')
        elif k == "highlight":
            out.append(f'you look at the {label or "result"}')
        elif k == "scroll_to":
            out.append(f'you scroll to the {label or "next part"}')
    return out


def _beat_labels(demo):
    """Har narrated step ka chhota naam (agar LLM kam jumle de to bharne ke kaam aata hai)."""
    steps = demo.get("steps", []) if demo else []
    out = []
    for i in narrated_indices(steps):
        s = steps[i]
        out.append(str(s.get("label") or "tool"))
    return out


def _shown_text(demo):
    """Policy reviewer ke liye: video mein jo dikhta hai, saaf lafzon mein."""
    if not demo:
        return ""
    parts = [str(demo.get("title", "")).strip()]
    parts += _beat_texts(demo)
    return " | ".join(p for p in parts if p)


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


def _local_problems(text, intro=None, has_beats=True, tool_name=None):
    """Agents ke andar hi lambai, repetition aur risky lafz ka check (LLM ko wapas dikhane ke liye)."""
    probs = []
    if intro is not None and has_beats:
        iw = _wc(intro)
        if iw > INTRO_MAX:
            probs.append(f"The intro is {iw} words, too LONG (the screen would stay still for too long). "
                         f"The intro must be 2 very short sentences, {INTRO_MIN}-{INTRO_MAX} words in total. "
                         "Move the extra explanation into the beat sentences.")
        elif iw < INTRO_MIN:
            probs.append(f"The intro is only {iw} words. It must be 2 short sentences, {INTRO_MIN}-{INTRO_MAX} words.")
        if tool_name and tool_name.lower() not in intro.lower():
            probs.append(f'The intro must name the tool exactly as "{tool_name}".')
    w = _wc(text)
    if w < TARGET_MIN:
        probs.append(f"Total length is {w} words, too SHORT. It must be {TARGET_MIN}-{TARGET_MAX} words "
                     f"(aim for {TARGET_AIM}). Add about {TARGET_AIM - w} more words to the beat sentences, "
                     "with NEW information about what each shown part does.")
    elif w > TARGET_MAX:
        probs.append(f"Total length is {w} words, too LONG. It must be {TARGET_MIN}-{TARGET_MAX} words "
                     f"(aim for {TARGET_AIM}). Remove about {w - TARGET_AIM} words.")
    for ph in _repeated_phrases(text):
        probs.append(f'The phrase "{ph}" is used more than once. Say each idea or feature list only ONCE '
                     "in the whole narration and use different words everywhere else.")
    for b in policy.find_banned(text):
        probs.append(f'Remove the risky phrase "{b}" (speed, time-saving and frequency claims are not allowed).')
    low = " " + re.sub(r"[^a-z ]", " ", text.lower()) + " "
    for a in ABSTRACT:
        if re.search(r"\b" + re.escape(a), low):
            probs.append(f'Replace the vague word "{a}" with plain everyday words that say exactly what the screen shows '
                         "(for example: you move the slider, the size goes down).")
    for c in policy.find_cta(text):
        probs.append(f'Remove the call to action "{c}".')
    return probs


def idea_and_script(tool, info, recent, policies, site_name, v, recent_openers, issues=None):
    demo = _resolve_demo(tool, v.get("demo"))
    beats = _beat_texts(demo)
    n = len(beats)
    name = tool.get("name", "this tool")
    desc = tool.get("description") or (info or {}).get("description", "")
    closing = make_closing(tool, demo)
    shown = _shown_text(demo)
    demo_title = (demo or {}).get("title", "")

    if n:
        # intro (~15) + closing (~10-13) nikal kar baqi beats mein baanto
        bw = max(8, min(30, round((TARGET_AIM - 15 - _wc(closing)) / n)))
        beat_list = "\n".join(f"Beat {i + 1}: {b}" for i, b in enumerate(beats))
        sent_rule = "ONE sentence" if bw <= 22 else "one or two short sentences"
        beat_rule = (f'"beats": a list of EXACTLY {n} items, one for each beat above, in the same order. '
                     f"Each item is {sent_rule} of about {bw} words and it is DIFFERENT from every other item. "
                     "While that beat happens on screen, the item says what is happening and what that "
                     "part of the tool is for.")
        intro_rule = (f'"intro": 2 very short sentences, {INTRO_MIN}-{INTRO_MAX} words in total. '
                      "Sentence 1 is the hook: a plain everyday problem this tool helps with, as a statement or "
                      "a question (no claim about how often or how much it happens). "
                      f'Sentence 2 names the tool exactly as "{name}". It is spoken while the tool is shown '
                      "before anything moves, so it must stay short.")
    else:
        beat_list = "(no separate beats)"
        beat_rule = '"beats": an empty list [].'
        intro_rule = ("\"intro\": 6-7 short sentences, about 92 words in total, each sentence about a different "
                      "part of what is shown. Sentence 1 is the hook: a plain everyday problem this tool helps with.")

    def make_prompt(extra):
        return f"""Write the voice-over for a 45 second vertical Short. The viewer sees a real screen
recording of this free browser tool being used, and hears your narration over it.
The narration is split into parts, and each part is spoken exactly while its beat is on screen.
Your job is to EXPLAIN the tool clearly.

Tool: {name}
Tool description (the ONLY source of facts about the tool): {desc}

WHAT THIS VIDEO SHOWS (nothing else is shown): {demo_title}
Beats on screen, in order:
{beat_list}

SCOPE RULE (very important): the description may list more features than this video shows.
Talk ONLY about what the beats show. Never name a category, option, unit type, file format or mode
from the description that does not appear in the beats (example: if the video only converts length,
do not say it converts weight or anything else). If you need to say what the tool is, use a general
phrase such as "a free {name}".
Also never mention another task (resizing, cropping, converting, merging, editing...) unless a beat shows it.

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
(The closing sentence is added by the system. Do NOT write a closing.)

Rules:
- Explain what each shown part DOES, in simple words, but never mention any feature that is not shown.
- NO REPETITION: every sentence must say something new. Never repeat a phrase and never copy long
  phrases from the tool description.
- Do NOT say the word "button" and do not mention clicking, unless a click beat is listed above.
- Do not read out exact results, numbers or counts, because you cannot see them.
- Use plain, literal words that a child could follow. Say what the beat says (for example: you move the
  quality slider to fifty). Never use vague or technical-sounding words such as: {ABSTRACT_TXT}.
  Do not describe effects that the screen does not show.
- No superlatives (best, #1, fastest), no stats.
- No claims about speed or time saved, and no claims about how often or how much a problem happens.
  NEVER use any of these words or phrases: {AVOID}.
- Do not use filler about the video itself: never say recording, video, step, "quick look", "follow along",
  "watch the screen" or "ongoing".
- Say "type" only when a type beat is listed; do not say "paste" unless the beat says so.
- NO call to action of any kind. Never use these words or anything like them: {NO_CTA}.
  Never tell the viewer to do anything and never mention a profile, a link or a website address.
- Do not say or write any URL.
- Short sentences, easy to speak. LENGTH IS STRICT: intro + all beats + the closing sentence
  ("{closing}") together must be {TARGET_MIN}-{TARGET_MAX} words (aim for {TARGET_AIM}).
  Count the words before answering. The intro must stay at {INTRO_MIN}-{INTRO_MAX} words.

Return JSON only: {{"topic": "short topic label", "intro": "...", "beats": ["..."]}}"""

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
        probs = _local_problems(" ".join([intro] + got + [closing]), intro, n > 0, name)
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
    segments = [intro] + got + [closing]
    segments = [s for s in segments if s]
    plan["segments"] = segments
    plan["n_beats"] = max(0, len(segments) - 2)
    plan["narration"] = " ".join(segments)
    plan["demo_id"] = (demo or {}).get("id", "")
    plan["shown"] = shown
    plan.setdefault("topic", f"{name} walkthrough")
    return plan


# Safe fallback: LLM script policy mein fail ho to ye chalta hai. Koi LLM nahi, koi generic filler nahi.
# Har jumla demo ke asal step se banta hai (kya hua + screen par kya dikhta hai), phir ek recap.
_CONNECT = ["First,", "Next,", "Then,", "After that,", "Now,", "Here,", "Finally,"]


def _effect(step):
    """Step ke baad screen par jo sach mein dikhta hai (har tool par sach, koi naya claim nahi)."""
    k = _norm_step(step)
    label = step.get("label") or ""
    if k == "type":
        return f"The text appears in the {label or 'box'}."
    if k == "click":
        return "You can see the page change."
    if k in ("select", "set"):
        return f"The {label or 'option'} now shows {step.get('value', '')}."
    if k == "upload":
        return "The file appears on the page."
    if k == "highlight":
        return f"The highlight marks the {label or 'result'}."
    if k == "scroll_to":
        return f"The page moves to the {label or 'next part'}."
    return ""


def fallback_script(tool, info, demo, v, policies):
    """Agar LLM script retry ke baad bhi policy pass na kare, to ye safe script chalta hai."""
    demo = _resolve_demo(tool, demo)
    name = tool.get("name", "this tool")
    steps = (demo or {}).get("steps", [])
    idx = narrated_indices(steps)
    beats = _beat_texts(demo)
    n = len(beats)
    title = str((demo or {}).get("title", "")).strip().rstrip(".")

    intro = f"{title} with the {name}. Here is how it works." if title else f"This is the {name}. Here is how it works."
    closing = make_closing(tool, demo)

    def build(with_effect):
        segs = []
        for j, (i, t) in enumerate(zip(idx, beats)):
            seg = f"{_CONNECT[j % len(_CONNECT)] if n <= len(_CONNECT) else ('Finally,' if j == n - 1 else 'Then,')} {t}."
            if with_effect:
                e = _effect(steps[i])
                if e:
                    seg += " " + e
            segs.append(seg)
        return segs

    recap = ("To recap: " + ", ".join(beats[:-1]) + (", and " if len(beats) > 1 else "") + beats[-1] + "."
             if beats else "")
    segs = build(True)
    tail = (recap + " " + closing).strip()
    # bahut lambi ho to pehle recap, phir effects hatao (video 60s se upar na jaye)
    if n and _wc(intro) + sum(_wc(s) for s in segs) + _wc(tail) > TARGET_MAX:
        tail = closing
    if n and _wc(intro) + sum(_wc(s) for s in segs) + _wc(tail) > TARGET_MAX:
        segs = build(False)
    segments = [intro] + segs + [tail]
    return {
        "topic": f"{name} basic walkthrough",
        "segments": segments,
        "n_beats": n,
        "narration": " ".join(segments),
        "demo_id": (demo or {}).get("id", ""),
        "shown": _shown_text(demo),
    }


def _clean_tags(meta, plan, tool, shown=""):
    """Galat/doosre-tool ke tags hatao; tool ka apna naam-tag zaroor rakho."""
    yt = meta.get("youtube", {}) if isinstance(meta, dict) else {}
    allowed = " ".join([str(plan.get("narration", "")), str(shown), str(tool.get("name", "")),
                        str(yt.get("title", ""))]).lower()
    own = re.sub(r"[^A-Za-z0-9]", "", str(tool.get("name", "")))

    def ok(t):
        tl = str(t).strip().lstrip("#").lower()
        if not tl or tl in GENERIC_TAGS:
            return False
        return not any(w in tl and w not in allowed for w in TASK_WORDS)

    for plat in ("youtube", "facebook", "instagram"):
        d = meta.get(plat)
        if not isinstance(d, dict):
            continue
        for key in ("tags", "hashtags"):
            if isinstance(d.get(key), list):
                kept = [str(t).strip().lstrip("#") for t in d[key] if ok(t)]
                if own and own.lower() not in [k.lower() for k in kept]:
                    kept.insert(0, own)
                d[key] = kept
    return meta


def metadata(plan, tool, policies, recent_titles=(), info=None):
    desc = tool.get("description") or ((info or {}).get("description", "") if isinstance(info, dict) else "")
    demo = _resolve_demo(tool, plan.get("demo_id"))
    shown = plan.get("shown") or _shown_text(demo)
    prompt = f"""Write separate, platform-specific text for the same short video.
Video topic: {plan['topic']}
Voice-over: {plan['narration']}
Tool: {tool['name']}
Tool description (the ONLY source of facts about the tool): {desc}

WHAT THE VIDEO ACTUALLY SHOWS (nothing else is shown): {shown}
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
SCOPE RULE: title, description, captions, tags and hashtags may only mention what the video shows.
The description may list more features than the video shows; do NOT name any feature, option, unit type,
file format or mode that is not in the "actually shows" line above (example: if only length is converted,
never say it converts weight). Describe what is shown with plain verbs (convert, count, merge, resize...).
Do NOT claim anything about the tool that is not in the tool description above or in the voice-over
(for example: "no sign up", "no registration", "no download", "private", "works offline", "always free").
Do not start any text with "This video shows", "In this video" or "Watch". Talk about the task itself.
Tags and hashtags must never name another task (resize, crop, convert, merge, edit...) unless the video shows it.
Tags and hashtags: at least two must name this tool or what is shown (for example the tool name without spaces
and the main action). Do not use generic tags such as tools, free, online, math, viral, trending, fyp.

The three texts must be different in wording (not copy-paste), each in the style of its platform.
Hashtags: words only, without the # sign, no spaces.

Return JSON only:
{{"youtube": {{"title": "", "description": "", "tags": ["..."], "hashtags": ["..."]}},
  "facebook": {{"caption": "", "hashtags": ["..."]}},
  "instagram": {{"caption": "", "hashtags": ["..."]}}}}"""
    meta = ask_json(prompt, SYSTEM, 0.8)
    try:
        return _clean_tags(meta, plan, tool, shown)
    except Exception:
        return meta


def fix_metadata(platform, plan, current, issues, policies):
    prompt = f"""Fix this {platform} text so it fully follows the rules. Keep the same JSON keys.
Video topic: {plan['topic']}
What the video actually shows (do not mention anything else): {plan.get('shown', '')}
Current text: {current}
Problems found: {issues}

Rules:
{policies['general']}
{policies[platform]}
NEVER use any of these words or phrases: {AVOID}.
Hashtags: words only, no # sign. Do not write URLs.

Return JSON only with the same keys as the current text."""
    return ask_json(prompt, SYSTEM, 0.5)
