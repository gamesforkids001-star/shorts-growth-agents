import os, json, datetime, pathlib, traceback, yaml
from . import site, agents, policy, video, publish, schedule, variety, record

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "output"
STATE = ROOT / "state" / "history.json"

REQUIRED = {
    "youtube": ["YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"],
    "facebook": ["META_PAGE_ID", "META_PAGE_TOKEN"],
    "instagram": ["IG_USER_ID", "META_PAGE_TOKEN"],
}


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


def main():
    cfg = yaml.safe_load((ROOT / "config" / "settings.yaml").read_text())
    pol = yaml.safe_load((ROOT / "config" / "policies.yaml").read_text())
    dry = (os.getenv("DRY_RUN") or str(cfg["dry_run"])).strip().lower() == "true"
    print("DRY RUN" if dry else "LIVE RUN")
    OUT.mkdir(parents=True, exist_ok=True)

    history = load_state()
    force = os.getenv("FORCE", "").strip().lower() == "true"
    slot = -1
    if not force:
        run, slot, q, why = schedule.should_run(history, cfg)
        print(f"quota={q}/day slot={slot}: {why}")
        if not run:
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
    info = site.page_info(tool)
    recent = [h.get("topic") for h in history[-30:]]
    v = variety.choose(history, tool)
    openers = [h.get("opener") for h in history[-12:] if h.get("opener")]
    demo = find_demo(tool, v.get("demo"))
    if not demo:
        raise SystemExit("is tool ka demo nahi mila: " + str(v.get("demo")))
    print("Tool:", tool["name"], "| demo:", demo.get("id"), "| format:", v["format"],
          "| hook:", v["hook"], "| voice:", v["voice"])

    # 1) idea + narration, policy-reviewed
    plan = None
    issues = None
    for _ in range(3):
        cand = agents.idea_and_script(tool, info, recent, pol, cfg["site_name"], v, openers, issues)
        ok, issues = policy.review_script(cand, pol, tool, v["demo"], openers)
        print("script ok:", ok, issues)
        if ok:
            plan = cand
            break
    if not plan:
        raise SystemExit("Script policy check pass nahi hua, aaj video skip")

    narration = plan["narration"]
    demo_id = plan.get("demo_id") or demo.get("id")
    # agar agent ne koi aur demo id di ho to wahi chalao, warna chuna hua demo
    demo = find_demo(tool, demo_id) or demo

    # 2) separate metadata per platform, each policy-checked
    platforms = [p for p, on in cfg["platforms"].items() if on]
    titles = [h.get("title") for h in history[-12:] if h.get("title")]
    meta = agents.metadata(plan, tool, pol, titles, info)
    final, report = {}, {}
    for p in platforms:
        m = meta.get(p, {})
        for _ in range(3):
            issues = policy.hard_check(p, m)
            if not issues:
                issues = policy.ai_check(p, plan, m, pol)
            if not issues:
                final[p] = compose(p, m, tool["url"], cfg["site_name"])
                break
            print(p, "issues:", issues)
            m = agents.fix_metadata(p, plan, m, issues, pol)
        else:
            report[p] = "skipped: policy check pass nahi hua"

    # 3) awaaz pehle (har jumla alag), phir recording usi ke hisab se ruk-ruk kar
    segs = plan.get("segments") or [narration]
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
        rec_path, trim_start, marks = record.record_demo(
            tool, demo, str(OUT / "rec"), max_seconds=cfg["max_seconds"], repo_root=str(ROOT),
            holds=holds, intro_hold=intro_hold, closing_hold=closing_hold)
    except record.BotCheckError as e:
        raise SystemExit("Bot-check aya, video skip: " + str(e))
    except Exception as e:
        traceback.print_exc()
        raise SystemExit("Recording fail, video skip: " + str(e))
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
        raise SystemExit("Video check fail, upload nahi: " + str(why))
    (OUT / "metadata.json").write_text(json.dumps(final, indent=2, ensure_ascii=False))

    # 5) publish
    for p, m in final.items():
        missing = [k for k in REQUIRED[p] if not os.getenv(k)]
        if dry:
            report[p] = "dry-run: post nahi kiya"
        elif missing:
            report[p] = f"skipped: secrets missing {missing}"
        else:
            try:
                if p == "youtube":
                    report[p] = "posted id=" + publish.youtube(path, m, cfg["youtube_privacy"])
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
    elif not dry:
        print("Kisi platform par post nahi hui, slot done nahi maana, agla run dobara koshish karega")
    (OUT / "report.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
