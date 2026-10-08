from .llm import ask_json
from .variety import FORMATS, HOOKS

SYSTEM = (
    "You are a careful content team for a small free-tools website. "
    "Be honest, original and helpful. Never invent facts, features or statistics."
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
            lines.append(f'the "{s.get("label") or s.get("selector", "a button")}" button is clicked')
        elif do == "select":
            lines.append(f'the option "{s.get("value", "")}" is chosen')
        elif do == "upload":
            lines.append("a small sample file is added")
    return f'{demo.get("title", "")}. On screen: ' + "; then ".join(lines) + "."


def idea_and_script(tool, info, recent, policies, site_name, v, recent_openers, issues=None):
    demo = v.get("demo")
    cta = v["cta"].format(site=site_name)
    fix = f"\nA previous draft had these problems, fix them: {issues}\n" if issues else ""
    prompt = f"""Write the voice-over for a 30-40 second vertical Short. The viewer sees a real screen
recording of this free browser tool being used, and hears your narration over it.

Tool: {tool['name']}
Tool description (the ONLY source of facts): {info['text']}

What happens on screen (your narration must match this, and must not describe anything else):
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
- Do not read out exact results, numbers or counts, because you cannot see them. Say things like "and the result shows up right away".
- Only claim what the tool description supports. No superlatives (best, #1, fastest), no stats.
- Do not say or write any URL.
- The narration must END with exactly this sentence: "{cta}"
- Total 55-85 words including that last sentence.

Return JSON only: {{"topic": "short topic label", "narration": "the full voice-over text"}}"""
    plan = ask_json(prompt, SYSTEM, 0.9)
    text = " ".join(str(plan.get("narration", "")).split())
    if cta not in text:
        text = (text + " " + cta).strip()
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
Hashtags: words only, no # sign. Do not write URLs.

Return JSON only with the same keys as the current text."""
    return ask_json(prompt, SYSTEM, 0.5)
