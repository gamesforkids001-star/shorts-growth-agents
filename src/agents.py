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


def _describe_demo(demo):
    """Demo ke steps ko seedhe lafzon mein likhta hai, taake narration wahi bole jo screen par ho raha hai."""
    if not demo:
        return "No fixed demo. Describe using the tool in general terms only."
    lines = []
    for s in demo.get("steps", []):
        do = s.get("do")
        if do == "type":
            lines.append(f'the text "{s.get("text", "")}" is typed into the tool')
        elif do == "click":
            lines.append(f'the "{s.get("label") or s.get("selector", "a control")}" control is clicked')
        elif do == "select":
            lines.append(f'the option "{s.get("value", "")}" is chosen')
        elif do == "upload":
            lines.append("a small sample file is added")
    return f'{demo.get("title", "")}. On screen: ' + "; then ".join(lines) + "."


def idea_and_script(tool, info, recent, policies, site_name, v, recent_openers, issues=None):
    demo = v.get("demo")
    fix = f"\nA previous draft had these problems, fix them: {issues}\n" if issues else ""
    prompt = f"""Write the voice-over for a 30-40 second vertical Short. The viewer sees a real screen
recording of this free browser tool being used, and hears your narration over it.

Tool: {tool['name']}
Tool description (the ONLY source of facts): {info['text']}

What happens on screen (your narration must match this exactly, and must not describe anything else):
{_describe_demo(demo)}

Recent topics (do NOT repeat the angle or wording): {recent}

Policy rules you must follow:
{policies['general']}

Video format for THIS video: {FORMATS[v['format']]}
Opening style: {HOOKS[v['hook']]}
Recent opening lines used before (start differently, do not reuse their pattern): {recent_openers}
{fix}
Rules:
- Speak naturally, as one flowing piece, not a list of separate scenes.
- Talk ONLY about the on-screen steps listed above. Do NOT list or mention any feature of the tool
  that is not one of those on-screen steps (for example, do not say what else the tool can count or check).
- Do NOT say the word "button" and do not mention clicking, unless a click step is listed above.
- Do not read out exact results, numbers or counts, because you cannot see them. If you mention the
  outcome at all, keep it vague, for example "and you can see the tool respond".
- No superlatives (best, #1, fastest), no stats.
- NEVER use any of these words or phrases: {AVOID}. Use plain words like "quickly" instead of "instantly".
- NO call to action of any kind. Never use these words or anything like them: {NO_CTA}.
  Never tell the viewer to do anything and never mention a profile, a link or a website address.
- Do not say or write any URL.
- End with one short, plain closing sentence that only states what was shown
  (example style: "That is the {tool['name']}, a free tool that runs in the browser."). It must not ask or tell the viewer to do anything.
- Total 40-65 words.

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
