from .llm import ask_json
from .variety import FORMATS, HOOKS

SYSTEM = (
    "You are a careful content team for a small free-tools website. "
    "Be honest, original and helpful. Never invent facts, features or statistics."
)


def idea_and_script(tool, info, recent, policies, site_name, v, recent_openers):
    prompt = f"""Write a 25-35 second vertical Short about this free browser tool.

Tool: {tool['name']}
Page title: {info['title']}
Page description: {info['description']}
Page text (the ONLY source of facts): {info['text']}

Recent topics (do NOT repeat the angle or wording): {recent}

Policy rules you must follow:
{policies['general']}

Video format for THIS video: {FORMATS[v['format']]}
Opening style: {HOOKS[v['hook']]}
Recent opening lines used before (start differently, do not reuse their pattern): {recent_openers}
Only use what the page text supports. The LAST scene must be exactly this sentence: "{v['cta'].format(site=site_name)}"
No superlatives (best, #1, fastest), no numbers or stats unless in the page text.

Return JSON only: {{"topic": "short topic label", "scenes": ["sentence 1", "sentence 2", ...]}}
5 to 7 scenes. Each scene is ONE spoken sentence, max 14 words. Total 55-80 words."""
    return ask_json(prompt, SYSTEM, 0.9)


def metadata(plan, tool, policies, recent_titles=()):
    prompt = f"""Write separate, platform-specific text for the same short video.
Video topic: {plan['topic']}
Script: {' '.join(plan['scenes'])}
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
