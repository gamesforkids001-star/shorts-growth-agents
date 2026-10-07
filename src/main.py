import os, json, datetime, pathlib, traceback, yaml
from . import site, agents, policy, video, publish, schedule, variety

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


def main():
    cfg = yaml.safe_load((ROOT / "config" / "settings.yaml").read_text())
    pol = yaml.safe_load((ROOT / "config" / "policies.yaml").read_text())
    dry = (os.getenv("DRY_RUN") or str(cfg["dry_run"])).strip().lower() == "true"
    print("DRY RUN" if dry else "LIVE RUN")

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
        raise SystemExit("Sitemap se koi tool page nahi mila")
    tool = site.pick_tool(tools, history)
    info = site.page_info(tool["url"])
    recent = [h.get("topic") for h in history[-30:]]
    v = variety.choose(history)
    openers = [h.get("opener") for h in history[-12:] if h.get("opener")]
    print("Tool:", tool["name"], "| format:", v["format"], "| hook:", v["hook"], "| voice:", v["voice"])

    # 1) idea + script, policy-reviewed
    plan = None
    for _ in range(3):
        cand = agents.idea_and_script(tool, info, recent, pol, cfg["site_name"], v, openers)
        ok, issues = policy.review_script(cand, pol)
        print("script ok:", ok, issues)
        if ok:
            plan = cand
            break
    if not plan:
        raise SystemExit("Script policy check pass nahi hua, aaj video skip")

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

    # 3) video (one file for all platforms)
    path, secs = video.build(plan["scenes"], tool["name"], v["voice"], str(OUT), cfg["max_seconds"])
    print(f"video ready: {secs:.0f}s")
    (OUT / "metadata.json").write_text(json.dumps(final, indent=2, ensure_ascii=False))

    # 4) publish
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

    if not dry:
        schedule.set_start_if_missing()
        history.append({"date": schedule.today_utc().isoformat(), "slot": slot, "tool": tool["slug"],
                        "topic": plan["topic"], "format": v["format"], "hook": v["hook"],
                        "cta": v["cta"], "voice": v["voice"], "opener": plan["scenes"][0],
                        "title": final.get("youtube", {}).get("title", ""), "results": report})
        STATE.write_text(json.dumps(history[-200:], indent=2))
    (OUT / "report.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
