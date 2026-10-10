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

_NUM_WORDS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}


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
            # file ginti saaf likho: 1 ho to "single/one", zyada ho to poori ginti (req 9: jo screen par wohi awaaz mein)
            n = len(s.get("files") or ([s.get("file") or s.get("path")] if (s.get("file") or s.get("path")) else [1]))
            what = label or "file"
            word = _NUM_WORDS.get(n, str(n))
            if n == 1:
                out.append(f'ONE single sample file is added ({what}); say "a single file" or "one file", '
                           'never "files", "multiple" or "several"')
            else:
                out.append(f'exactly {word} sample files are added together ({what}); say "{word} files", '
                           'never "a single file"')
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


def idea_and_script(tool, info, recent, policies, site_name, v, recent_openers, issues=None):
    demo = v.get("demo")
    fix = f"\nA previous draft had these problems, fix them: {issues}\n" if issues else ""
    beats = _beat_texts(demo)
    n = len(beats)
    if n:
        # intro (~22) + closing (~12) = ~34 words; baqi beats mein baanto, total ~96
        bw = max(8, min(22, round((96 - 34) / n)))
        beat_list = "\n".join(f"Beat {i + 1}: {b}" for i, b in enumerate(beats))
        beat_rule = (f'"beats": a list of EXACTLY {n} items, one for each beat above, in the same order. '
                     f"Each item is ONE short sentence of about {bw} words. While that beat happens on screen, "
                     "the sentence says what is happening and what that part of the tool is for.")
    else:
        beat_list = "(no separate beats)"
        beat_rule = '"beats": an empty list []. Put the whole explanation into "intro" (5-6 sentences, about 75 words).'

    prompt = f"""Write the voice-over for a 45 second vertical Short. The viewer sees a real screen
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
{fix}
Return these parts:
- "intro": 2 short sentences, about 22 words. Sentence 1 is the hook: a real everyday problem this tool solves,
  as a question or a plain statement. Sentence 2 names the tool and what it is for (tool description only).
  It is spoken while the tool is shown before anything moves.
- {beat_rule}
- "closing": 1 plain sentence, about 12 words, that only states what was shown.

Rules:
- Explain what each shown part DOES, in simple words, but never mention any feature that is not in
  the tool description or not shown on screen.
- Do NOT say the word "button" and do not mention clicking, unless a click beat is listed above.
- Do not read out exact results, numbers or counts, because you cannot see them.
- No superlatives (best, #1, fastest), no stats.
- NEVER use any of these words or phrases: {AVOID}. Use plain words like "quickly" instead of "instantly".
- NO call to action of any kind. Never use these words or anything like them: {NO_CTA}.
  Never tell the viewer to do anything and never mention a profile, a link or a website address.
- FILE COUNTS: say exactly how many files are added in a beat (one single file, or two files, and so on).
  If a beat says ONE single file, never say "files", "multiple", "several" or "many". Say only what is on screen.
- Do not say or write any URL.
- The closing sentence must not ask or tell the viewer to do anything
  (example style: "That is the {tool['name']}, a free tool that runs in the browser.").
- Short sentences, easy to speak. LENGTH IS STRICT: intro + all beats + closing together must be
  92-102 words. Count before answering. Never more than 102 and never fewer than 92.

Return JSON only: {{"topic": "short topic label", "intro": "...", "beats": ["..."], "closing": "..."}}"""

    plan = None
    got = []
    for _ in range(3):
        plan = ask_json(prompt, SYSTEM, 0.9)
        got = _clean_beats(plan, n)
        if len(got) == n:  # poori ginti chahiye, warna dobara
            break
    # teen koshish ke baad bhi kam hon to baqi steps ke liye chhota jumla bhar do (sync na tute)
    if n and len(got) < n:
        labels = _beat_labels(demo)
        for j in range(len(got), n):
            got.append(f"Here is the {labels[j] if j < len(labels) else 'tool'}.")
    intro = " ".join(str(plan.get("intro", "")).split())
    closing = " ".join(str(plan.get("closing", "")).split())
    segments = [intro] + got + [closing]
    segments = [s for s in segments if s]
    # beats ginti: intro aur closing ke darmiyan
    plan["segments"] = segments
    plan["n_beats"] = max(0, len(segments) - 2)
    plan["narration"] = " ".join(segments)
    plan["demo_id"] = (demo or {}).get("id", "")
    return plan


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
