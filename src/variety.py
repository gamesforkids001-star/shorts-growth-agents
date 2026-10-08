"""Har video ko alag banane ke liye: format, hook, CTA, voice aur demo (screen par kya dikhega).
Recent history se bachta hai taake video repeat na ho."""
import random

FORMATS = {
    "quick_tip": "A practical quick tip: hook with a real everyday problem, then show how the tool helps while the demo plays.",
    "myth_vs_fact": "Start with a common wrong assumption people have about this kind of task, then gently correct it while the demo plays.",
    "question": "Open with a relatable question, then answer it step by step as the demo plays on screen.",
    "mini_story": "A tiny 'imagine this' everyday situation (no fake names, no fake people), then show how the tool solves it on screen.",
    "three_steps": "Explain how to use the tool in 3 simple steps, matching exactly what is happening on screen.",
    "before_after": "Contrast the slow, annoying old way of doing the task with the simpler way shown on screen.",
    "mistake_to_avoid": "Point out a common mistake people make with this task, then the safer way shown on screen.",
    "checklist": "A short 'before you do this, check these things' list, then the tool as the easy way to finish.",
    "when_to_use": "Mention 2-3 real situations when this tool is handy while the demo plays.",
}

HOOKS = {
    "question": "Open with a short question.",
    "problem": "Open by naming a common frustration in plain words.",
    "stop": "Open with a gentle 'Stop doing X the hard way' style line (no shouting).",
    "if_you": "Open with 'If you ever ...' style line.",
    "quick_one": "Open with a casual 'Quick one:' or 'Small tip:' style line.",
    "imagine": "Open with 'Imagine ...' and a relatable moment.",
    "fact": "Open with a calm, true statement taken from the tool description.",
}

CTAS = [
    "Try it free on {site}. Link in my profile.",
    "It is free to use on {site}. The link is in my profile.",
    "You can open it on {site}. Check my profile for the link.",
    "Find it free on {site}, link in my profile.",
    "Give it a try on {site}. My profile has the link.",
    "Free on {site}. Tap the link in my profile to try it.",
]

VOICES = [
    "en-US-AriaNeural", "en-US-GuyNeural", "en-US-JennyNeural", "en-US-DavisNeural",
    "en-GB-SoniaNeural", "en-GB-RyanNeural", "en-AU-NatashaNeural", "en-IN-NeerjaNeural",
]


def _pick(options, recent, avoid=4):
    banned = set(r for r in recent[-avoid:] if r)
    pool = [o for o in options if o not in banned] or list(options)
    return random.choice(pool)


def _pick_demo(tool, history):
    """Is tool ki sab se kam use hui demo chunta hai (aur pichli wali dobara nahi)."""
    demos = (tool or {}).get("demos") or []
    if not demos:
        return None
    slug = tool.get("slug")
    used = [h.get("demo") for h in history if h.get("tool") == slug and h.get("demo")]
    counts = {d["id"]: used.count(d["id"]) for d in demos}
    lowest = min(counts.values())
    last = used[-1] if used else None
    pool = [d for d in demos if counts[d["id"]] == lowest and d["id"] != last]
    if not pool:
        pool = [d for d in demos if counts[d["id"]] == lowest]
    return random.choice(pool)


def choose(history, tool=None):
    return {
        "format": _pick(list(FORMATS), [h.get("format") for h in history], 4),
        "hook": _pick(list(HOOKS), [h.get("hook") for h in history], 3),
        "cta": _pick(CTAS, [h.get("cta") for h in history], 3),
        "voice": _pick(VOICES, [h.get("voice") for h in history], 2),
        "demo": _pick_demo(tool, history),
}
