"""v12: record.py marks["cut"] ho to YouTube par Private, Facebook/Instagram par skip."""
import os, json, datetime, pathlib, traceback, yaml
from . import site, agents, policy, video, publish, schedule, variety, record, llm

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "output"
STATE = ROOT / "state" / "history.json"

REQUIRED = {
    "youtube": ["YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"],
    "facebook": ["FB_PAGE_ID", "FB_PAGE_ACCESS_TOKEN"],
    "instagram": ["IG_USER_ID", "IG_ACCESS_TOKEN"],
}


class Skip(Exception):
    """Video aaj skip hui, lekin ye error nahi hai (exit code 0)."""


def load_state():
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return []


def clean(tags):
    return policy.clean_tags(tags)


def compose(platform, m, url, site_name):
    tags = clean(m.get("hashtags"))
    hs = " ".join("#" + t for t in tags)
    if platform == "youtube":
        return {
            "title": m["title"].strip(),
            "description": f"{m['description'].strip()}\n\nFree tool: {url}\n\n{hs} #Shorts",
            "tags": clean(m.get("tags"))[:10],
        }
    if platform == "facebook":
        return {"caption": f"{m['caption'].strip()}\n\nFree tool: {url}\n\n{hs}"}
    return {"caption": f"{m['caption'].strip()}\n\nLink in bio: {site_name}\n\n{hs}"}


def _snip(text, limit):
    """text ko limit ke andar, poore jumle par kaato."""
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    i = max(cut.rfind(". "), cut.rfind("."))
    return (cut[:i + 1] if i > 40 else cut.rsplit(" ", 1)[0]).strip()


def fallback_meta(platform, plan, tool):
    """Gemini na chale to bina LLM ke safe text: sirf tool ka naam aur wohi narration jo pehle policy se guzri."""
    name = str(tool.get("name", "")).strip()
    own = "".join(ch for ch in name if ch.isalnum())
    narr = _snip(plan.get("narration", ""), 300)
    tags = [own, own + "Online", "OnlineTool", "BrowserTool", "WebTool", "EasyFileOnlineTools"]
    hashtags = [own, "OnlineTool", "BrowserTool"]
    if platform == "youtube":
        return {"title": f"{name} - free online tool demo"[:70],
                "description": f"{name}, a free tool for the browser. {narr}"[:590],
                "tags": tags, "hashtags": hashtags}
    if platform == "facebook":
        return {"caption": f"{name} walkthrough: {_snip(narr, 300)}"[:390], "hashtags": hashtags}
    return {"caption": f"{name} in the browser. {_snip(narr, 300)}"[:390], "hashtags": hashtags}


def demos_from_json():
    """tools_parts/*.json (ya purani tools.json) se har tool ke demos (slug -> list).
    Agar site.py demos na de to bhi chalega."""
    try:
        return {t["slug"]: t.get("demos") or [] for t in site.load_all()}
    except Exception:
        return {}


def find_demo(tool, ref):
    """ref dict ho, id (string) ho ya None: tool ka asli demo dict wapas do."""
    demos = tool.get("demos") or []
    if isinstance(ref, dict) and ref.get("steps"):
        return ref
    if isinstance(ref, str):
        for d in demos:
            if d.get("id") == ref:
                return d
    return None


def opener_of(narration):
    return " ".join(str(narration).split()[:6])


def video_ok(path, max_seconds):
    """publish.check_video ka result samjho: exception ya False = fail."""
    try:
        res = publish.check_video(path, max_seconds)
    except Exception as e:
        return False, str(e)
    if res is False:
        return False, "check_video ne False diya"
    if isinstance(res, (tuple, list)) and res and isinstance(res[0], bool):
        return res[0], (res[1] if len(res) > 1 else "")
    return True, ""


def run():
    cfg = yaml.safe_load((ROOT / "config" / "settings.yaml").read_text())
    pol = yaml.safe_load((ROOT / "config" / "policies.yaml").read_text())
    dry = (os.getenv("DRY_RUN") or str(cfg["dry_run"])).strip().lower() == "true"
    print("DRY RUN" if dry else "LIVE RUN")
    OUT.mkdir(parents=True, exist_ok=True)

    history = load_state()
    force = os.getenv("FORCE", "").strip().lower() == "true"
    slot = -1
    if not force:
        should, slot, q, why = schedule.should_run(history, cfg)
        print(f"quota={q}/day slot={slot}: {why}")
        if not should:
            return

    tools = site.list_tools(cfg["site_base"])
    if not tools:
        raise SystemExit("tools_parts se koi tool nahi mila")
    # demos tool mein na hon to tools_parts se jodo; sirf wohi tools lo jin ke demos hain
    dj = demos_from_json()
    for t in tools:
        if not t.get("demos"):
            t["demos"] = dj.get(t.get("slug"), [])
    playable = [t for t in tools if t.get("demos")]
    if not playable:
        raise SystemExit("kisi tool mein demos nahi hain (tools_parts check karo)")

    tool = site.pick_tool(playable, history)
    # ONLY_TOOL=<slug> ho to wahi tool (22 tools ki matrix dry run ke liye); khali ho to pehle jaisa
    only = os.getenv("ONLY_TOOL", "").strip()
    if only:
        match = [t for t in playable if t.get("slug") == only]
        if not match:
            raise SystemExit("ONLY_TOOL ka tool nahi mila: " + only)
        tool = match[0]
    info = site.page_info(tool)
    recent = [h.get("topic") for h in history[-30:]]
    v = variety.choose(history, tool)
    openers = [h.get("opener") for h in history[-12:] if h.get("opener")]
    demo = find_demo(tool, v.get("demo"))
    if not demo:
        raise SystemExit("is tool ka demo nahi mila: " + str(v.get("demo")))
    print("Tool:", tool["name"], "| demo:", demo.get("id"), "| format:", v["format"],
          "| hook:", v["hook"], "| voice:", v["voice"])

    # 1) idea + narration, policy-reviewed (har retry mein pichle issues LLM ko wapas jate hain)
    plan = None
    issues = None
    script_log = []
    for attempt in range(1, 4):
        try:
            cand = agents.idea_and_script(tool, info, recent, pol, cfg["site_name"], v, openers, issues)
            ok, issues = policy.review_script(cand, pol, tool, v["demo"], openers)
        except llm.LLMError as e:
            # Gemini nahi chala: crash nahi, seedha fallback script par
            print("Gemini fail, fallback script par ja rahe:", e)
            script_log.append({"attempt": attempt, "ok": False,
                               "issues": ["Gemini: " + str(e)[:300]], "narration": ""})
            OUT.mkdir(parents=True, exist_ok=True)
            (OUT / "script_log.json").write_text(json.dumps(script_log, indent=2, ensure_ascii=False))
            break
        print(f"script attempt {attempt}/3 ok:", ok, issues)
        script_log.append({"attempt": attempt, "ok": ok, "issues": issues,
                           "narration": cand.get("narration", "")})
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "script_log.json").write_text(json.dumps(script_log, indent=2, ensure_ascii=False))
        if ok:
            plan = cand
            break

    if not plan:
        # safe fallback script (agents.fallback_script, agar agents.py mein ho)
        fb = getattr(agents, "fallback_script", None)
        if fb:
            try:
                plan = fb(tool, info, demo, v, pol)
                print("FALLBACK script use hua (3 retry fail hone ke baad)")
            except Exception as e:
                traceback.print_exc()
                print("fallback script bhi fail:", e)
                plan = None
        if not plan:
            raise Skip("Script policy check 3 retry ke baad pass nahi hua aur fallback nahi mila. "
                       "Last issues: " + str(issues))

    narration = plan["narration"]
    demo_id = plan.get("demo_id") or demo.get("id")
    # agar agent ne koi aur demo id di ho to wahi chalao, warna chuna hua demo
    demo = find_demo(tool, demo_id) or demo

    # 2) separate metadata per platform, each policy-checked
    platforms = [p for p, on in cfg["platforms"].items() if on]
    titles = [h.get("title") for h in history[-12:] if h.get("title")]
    try:
        meta = agents.metadata(plan, tool, pol, titles, info)
    except llm.LLMError as e:
        print("Gemini fail (metadata), safe text use ho raha hai:", e)
        meta = {}
    final, report = {}, {}
    for p in platforms:
        m = meta.get(p) or fallback_meta(p, plan, tool)
        for _ in range(3):
            issues = policy.hard_check(p, m)
            if not issues:
                try:
                    issues = policy.ai_check(p, plan, m, pol)
                except llm.LLMError as e:
                    # AI check nahi chala: LLM ka likha text bhej nahi sakte, safe text lo
                    print(p, "AI check nahi chala, safe text use:", e)
                    m = fallback_meta(p, plan, tool)
                    issues = policy.hard_check(p, m)
            if not issues:
                final[p] = compose(p, m, tool["url"], cfg["site_name"])
                break
            print(p, "issues:", issues)
            try:
                m = agents.fix_metadata(p, plan, m, issues, pol)
            except llm.LLMError:
                m = fallback_meta(p, plan, tool)
        else:
            report[p] = "skipped: policy check pass nahi hua"

    # 3) awaaz pehle (har jumla alag), phir recording usi ke hisab se ruk-ruk kar
    segs = plan.get("segments") or [narration]
    # banned lafz (jaise "instantly") segments mein reh jate the: awaaz aur caption se pehle saaf karo
    segs = [policy.sanitize(x) for x in segs]
    narration = " ".join(segs)
    voices = video.make_voice(segs, v["voice"], str(OUT / "voice"))
    steps = demo.get("steps", [])
    idx = record.narrated_indices(steps)
    nb = max(0, len(voices) - 2)  # intro aur closing ke darmiyan ke jumle
    holds = [None] * len(steps)
    for k in range(min(nb, len(idx))):
        holds[idx[k]] = voices[1 + k]["dur"] + 0.4
    intro_hold = voices[0]["dur"] + 0.3
    closing_hold = (voices[-1]["dur"] + 0.3) if len(voices) >= 2 else 0.0

    try:
        rec_result = record.record_demo(
            tool, demo, str(OUT / "rec"), max_seconds=cfg["max_seconds"], repo_root=str(ROOT),
            holds=holds, intro_hold=intro_hold, closing_hold=closing_hold)

        if rec_result is None:
            raise Skip("Recording fail: record_demo ne None return kiya hai.")

        rec_path, trim_start, marks = rec_result
        cut = bool(marks.get("cut"))   # tool kat raha ho to video Public nahi hogi

    except Skip:
        raise
    except record.BotCheckError as e:
        raise Skip("Bot-check aya, video skip: " + str(e))
    except Exception as e:
        traceback.print_exc()
        raise Skip("Recording fail, video skip: " + str(e))
    print("recording:", rec_path, "trim_start:", trim_start, "marks:", marks)

    # har awaaz kab shuru ho: intro = 0, beats = un steps ka shuru-waqt, closing = aakhri step ke baad
    starts = [0.0]
    for k in range(nb):
        si = idx[k] if k < len(idx) else None
        starts.append(marks["steps"][si] if si is not None and si < len(marks["steps"]) else None)
    if len(voices) >= 2:
        starts.append(marks["end"])

    # 4) awaaz + captions + recording + aakhri CTA = ek video (sab platforms ke liye)
    path, secs = video.build(voices, tool["name"], str(OUT), cfg["max_seconds"],
                             rec_path, trim_start, starts)
    print(f"video ready: {secs:.0f}s")
    ok, why = video_ok(path, cfg["max_seconds"])
    if not ok:
        raise Skip("Video check fail, upload nahi: " + str(why))
    (OUT / "metadata.json").write_text(json.dumps(final, indent=2, ensure_ascii=False))

    # 5) publish
    for p, m in final.items():
        missing = [k for k in REQUIRED[p] if not os.getenv(k)]
        if dry:
            report[p] = "dry-run: post nahi kiya"
        elif missing:
            report[p] = f"skipped: secrets missing {missing}"
        elif cut and p != "youtube":
            report[p] = "skipped: video kat rahi thi (quality flag), sirf YouTube Private par gayi"
        else:
            try:
                if p == "youtube":
                    privacy = "private" if cut else cfg["youtube_privacy"]
                    report[p] = ("posted id=" + str(publish.youtube(path, m, privacy))
                                 + (" [PRIVATE: quality flag]" if cut else ""))
                elif p == "facebook":
                    report[p] = "posted id=" + str(publish.facebook(path, m["caption"]))
                else:
                    report[p] = "posted id=" + str(publish.instagram(path, m["caption"]))
            except Exception as e:
                traceback.print_exc()
                report[p] = f"FAILED: {e}"
    print(json.dumps(report, indent=2))

    posted_any = any(str(r).startswith("posted") for r in report.values())
    if not dry and posted_any:
        schedule.set_start_if_missing()
        history.append({"date": schedule.today_utc().isoformat(), "slot": slot, "tool": tool["slug"],
                        "demo": demo_id, "topic": plan["topic"], "format": v["format"],
                        "hook": v["hook"], "cta": v["cta"], "voice": v["voice"],
                        "opener": opener_of(narration),
                        "title": final.get("youtube", {}).get("title", ""), "results": report})
        STATE.write_text(json.dumps(history[-200:], indent=2))

    if not dry and not posted_any:
        print("Kisi platform par post nahi hui, slot done nahi maana, agla run dobara koshish karega")

    (OUT / "report.json").write_text(json.dumps(report, indent=2))


def main():
    try:
        run()
    except Skip as e:
        OUT.mkdir(parents=True, exist_ok=True)
        dry = (os.getenv("DRY_RUN") or "").strip().lower() == "true"
        tag = "SKIPPED (dry-run)" if dry else "SKIPPED"
        print(f"\n=== {tag}: aaj video nahi bani. Wajah: {e} ===")
        print("Ye error nahi hai, workflow exit code 0 ke saath khatam hoga.")
        (OUT / "report.json").write_text(json.dumps({"skipped": str(e)}, indent=2))
        # exit code 0: koi raise nahi
    except (Exception, SystemExit) as e:
        # kisi aur wajah se crash: asli sabab report.json aur error.txt mein likho (test summary mein dikhega)
        OUT.mkdir(parents=True, exist_ok=True)
        tb = traceback.format_exc()
        (OUT / "error.txt").write_text(tb)
        last = (str(e) or tb.strip().splitlines()[-1])[:300]
        (OUT / "report.json").write_text(json.dumps({"skipped": "CRASH: " + type(e).__name__ + ": " + last}, indent=2))
        raise


if __name__ == "__main__":
    main()
