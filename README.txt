SHORTS GROWTH AGENTS (YouTube + Facebook + Instagram)

Ek video roz banta hai, teeno platforms ke liye alag title/caption/tags/hashtags,
policy check ke baad auto post.

Pehle test (dry run): Actions > daily-shorts > Run workflow > dry_run = true
Video aur metadata.json "short-output" artifact mein milenge. Kuch post nahi hoga.

Secrets (Settings > Secrets and variables > Actions):
  GEMINI_API_KEY (pehle se hai)
  YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
  META_PAGE_ID, META_PAGE_TOKEN, IG_USER_ID

Live karne ke liye: config/settings.yaml mein dry_run: false
YouTube public karne ke liye: youtube_privacy: public (audit ke baad)
Rules badalne ke liye: config/policies.yaml

POSTING SCHEDULE (auto ramp-up, global timing, UTC):
  Din 1-15: 1/day (16:00 UTC) | 16-30: 2/day (+08:00) | 31-45: 3/day (+00:00)
  46-60: 4/day (+20:00) | 61-75: 5/day (+12:00) | 76+: 6/day (+04:00)
  Start date pehli LIVE post par khud set hoti hai (state/start.json). Dry run se start nahi hota.
  Manual "Run workflow" hamesha chalta hai (schedule ignore karta hai).
  Timing badalni ho to src/schedule.py (SLOT_HOURS_UTC, ACTIVE) aur workflow ki cron dono badlen.

CONTENT VARIETY (auto):
  Har video ka format (tip, myth vs fact, question, story, 3 steps...), opening style, CTA wording,
  awaaz (voice), rang aur layout badalta rehta hai. Recent videos jaisa kuch repeat nahi hota.
  Naye formats/CTA/voices chahiye to src/variety.py mein add karo.
