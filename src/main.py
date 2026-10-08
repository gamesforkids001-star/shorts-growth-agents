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
    """tools.json se har tool ke demos (slug -> list). Agar site.py demos na de to bhi chalega."""
    try:
        data = json.loads((ROOT / "tools.json").read_text(encoding="utf-8"))
        return {t["slug"]: t.get("demos") or [] for t in data}
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
        raise SystemExit("tools.json se koi tool nahi mila")
    # demos tool mein na hon to tools.json se jodo; sirf wohi tools lo jin ke demos hain
    dj = demos_from_json()
    for t in tools:
        if not t.get("demos"):
            t["demos"] = dj.get(t.get("slug"), [])
    playable = [t for t in tools if t.get("demos")]
    if not playable:
        raise SystemExit("kisi tool mein demos nahi hain (tools.json check karo)")

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
    meta = agents.metadata(plan, tool, pol, titles)
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

    # 3) asli tool ki screen recording (bot-check par skip)
    try:
        rec_path, trim_start = record.record_demo(
            tool, demo, str(OUT / "rec"), max_seconds=cfg["max_seconds"], repo_root=str(ROOT))
    except record.BotCheckError as e:
        raise SystemExit("Bot-check aya, video skip: " + str(e))
    except Exception as e:
        traceback.print_exc()
        raise SystemExit("Recording fail, video skip: " + str(e))
    print("recording:", rec_path, "trim_start:", trim_start)

    # 4) voice-over + captions + recording = ek video (sab platforms ke liye)
    path, secs = video.build(narration, tool["name"], v["voice"], str(OUT), cfg["max_seconds"],
                             rec_path, trim_start)
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
