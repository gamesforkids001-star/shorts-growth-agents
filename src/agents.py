from .llm import ask_json
from .variety import FORMATS, HOOKS

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


def _kind(s):
    """Step ka naam (purane 'do' aur naye 'action' dono chalte hain)."""
    return str(s.get("do") or s.get("action") or s.get("op") or s.get("type") or "").lower()


def _describe_demo(demo):
    """Demo ke steps ko seedhe lafzon mein likhta hai, taake narration wahi bole jo screen par ho raha hai."""
    if not demo:
        return "No fixed demo. Describe using the tool in general terms only."
    lines = []
    for s in demo.get("steps", []):
        k = _kind(s)
        if k == "type":
            lines.append(f'the text "{s.get("text", "")}" is typed into the tool')
        elif k == "click":
            lines.append(f'the "{s.get("label") or s.get("selector", "a control")}" control is clicked')
        elif k == "select":
            lines.append(f'the option "{s.get("value", "")}" is chosen')
        elif k == "upload":
            lines.append("a small sample file is added")
        elif k in ("highlight", "focus"):
            lines.append(f'the "{s.get("label") or "result"}" part of the tool is highlighted with a yellow frame')
        elif k == "scroll_to":
            lines.append(f'the view moves down to the "{s.get("label") or "next"}" part of the tool')
    return f'{demo.get("title", "")}. On screen: ' + "; then ".join(lines) + "."


def idea_and_script(tool, info, recent, policies, site_name, v, recent_openers, issues=None):
    demo = v.get("demo")
    fix = f"\nA previous draft had these problems, fix them: {issues}\n" if issues else ""
    prompt = f"""Write the voice-over for a 45 second vertical Short. The viewer sees a real screen
recording of this free browser tool being used, and hears your narration over it.
The tool fills the whole screen, so the viewer can read it. Your job is to EXPLAIN the tool clearly.

Tool: {tool['name']}
Tool description (the ONLY source of facts): {info['text']}

What happens on screen, in order (your narration follows this order):
{_describe_demo(demo)}

Recent topics (do NOT repeat the angle or wording): {recent}

Policy rules you must follow:
{policies['general']}

Video format for THIS video: {FORMATS[v['format']]}
Opening style: {HOOKS[v['hook']]}
Recent opening lines used before (start differently, do not reuse their pattern): {recent_openers}
{fix}
Structure (one flowing piece, no headings, no list):
1. Hook (1 sentence): a real everyday problem this tool solves, as a question or a plain statement.
2. What it is (1 sentence): name the tool and what it is for, using only the tool description.
3. Walk-through (5-7 sentences): go through the on-screen steps in order. When a part of the tool is
   highlighted, say what that part is for, using only facts from the tool description.
4. Closing (1 sentence): a plain sentence that only states what was shown.

Rules:
- Explain what each shown part DOES, in simple words, but never mention any feature that is not in
  the tool description or not shown on screen.
- Do NOT say the word "button" and do not mention clicking, unless a click step is listed above.
- Do not read out exact results, numbers or counts, because you cannot see them.
- No superlatives (best, #1, fastest), no stats.
- NEVER use any of these words or phrases: {AVOID}. Use plain words like "quickly" instead of "instantly".
- NO call to action of any kind. Never use these words or anything like them: {NO_CTA}.
  Never tell the viewer to do anything and never mention a profile, a link or a website address.
- Do not say or write any URL.
- The closing sentence must not ask or tell the viewer to do anything
  (example style: "That is the {tool['name']}, a free tool that runs in the browser.").
- Short sentences, easy to speak. LENGTH IS STRICT: aim for 100-115 words in total (about 45 seconds).
  Count your words before answering. Never write more than 115 words and never fewer than 95.
  If your draft is longer than 115 words, shorten the walk-through.

Return JSON only: {{"topic": "short topic label", "narration": "the full voice-over text"}}"""
    plan = ask_json(prompt, SYSTEM, 0.9)
    text = " ".join(str(plan.get("narration", "")).split())
    plan["narration"] = text
    plan["demo_id"] = (demo or {}).get("id", "")
    return plan


def metadata(plan, tool, policies, recent_titles=()):
    prompt = f"""Write separate, platform-specific text for the same short video.
Video topic: {plan['topic']}
Voice-over: {plan['narration']}
Tool: {tool['name']}
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
