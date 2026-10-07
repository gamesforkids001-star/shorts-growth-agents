"""Har video ko alag banane ke liye: format, hook style, CTA, voice, rang. Recent history se bachta hai."""
import random

FORMATS = {
    "quick_tip": "A practical quick tip: hook with a real everyday problem, then show how the tool helps.",
    "myth_vs_fact": "Start with a common wrong assumption people have about this kind of task, then gently correct it using the tool.",
    "question": "Open with a relatable question, then answer it step by step using the tool.",
    "mini_story": "A tiny 'imagine this' everyday situation (no fake names, no fake people), then how the tool solves it.",
    "three_steps": "Explain how to use the tool in 3 simple steps, taken only from the page text.",
    "before_after": "Contrast the slow, annoying old way of doing the task with the simpler way using the tool.",
    "mistake_to_avoid": "Point out a common mistake people make with this task, then the safer way using the tool.",
    "checklist": "A short 'before you do this, check these things' list, then the tool as the easy way to finish.",
    "when_to_use": "Explain 2-3 real situations when this tool is handy, one per scene.",
}

HOOKS = {
    "question": "Open with a short question.",
    "problem": "Open by naming a common frustration in plain words.",
    "stop": "Open with a gentle 'Stop doing X the hard way' style line (no shouting).",
    "if_you": "Open with 'If you ever ...' style line.",
    "quick_one": "Open with a casual 'Quick one:' or 'Small tip:' style line.",
    "imagine": "Open with 'Imagine ...' and a relatable moment.",
    "fact": "Open with a calm, true statement taken from the page text.",
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


def choose(history):
    return {
        "format": _pick(list(FORMATS), [h.get("format") for h in history], 4),
        "hook": _pick(list(HOOKS), [h.get("hook") for h in history], 3),
        "cta": _pick(CTAS, [h.get("cta") for h in history], 3),
        "voice": _pick(VOICES, [h.get("voice") for h in history], 2),
    }
