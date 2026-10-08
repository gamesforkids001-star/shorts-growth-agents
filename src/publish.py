import os, time, json, subprocess, requests

G = "https://graph.facebook.com/v21.0"


def check_video(path, max_seconds=60):
    """Upload se pehle video check: file ho, vertical ho, awaaz ho, lambai theek ho.
    Kuch ghalat ho to error deta hai, aur ghalat video kabhi upload nahi hoti."""
    if not os.path.exists(path) or os.path.getsize(path) < 50_000:
        raise ValueError("video file missing ya bohat chhoti hai")
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height",
         "-show_entries", "format=duration", "-of", "json", path],
        capture_output=True, text=True, check=True).stdout
    info = json.loads(out)
    streams = info.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    dur = float(info.get("format", {}).get("duration", 0))
    if not video:
        raise ValueError("video stream nahi mili")
    if int(video["height"]) <= int(video["width"]):
        raise ValueError("video vertical (9:16) nahi hai")
    if not has_audio:
        raise ValueError("video mein awaaz nahi hai")
    if dur < 10 or dur > max_seconds:
        raise ValueError(f"video ki lambai theek nahi: {dur:.0f}s")
    return dur


def _transient(e):
    """Sirf aise error par dobara koshish jo aksar waqti hote hain (503, network)."""
    if isinstance(e, (requests.ConnectionError, requests.Timeout)):
        return True
    status = getattr(getattr(e, "resp", None), "status", None)  # google HttpError
    if status is None:
        status = getattr(getattr(e, "response", None), "status_code", None)  # requests
    return status is not None and int(status) >= 500


def _retry(fn, tries=3, wait=30):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            if i == tries - 1 or not _transient(e):
                raise
            print(f"temporary error ({e}), {wait}s baad dobara koshish...")
            time.sleep(wait)


def _youtube_once(video, m, privacy):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    creds = Credentials(
        None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    yt = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {
            "title": m["title"],
            "description": m["description"],
            "tags": m["tags"],
            "categoryId": "28",
        },
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }
    req = yt.videos().insert(
        part="snippet,status", body=body,
        media_body=MediaFileUpload(video, mimetype="video/mp4", resumable=True, chunksize=-1))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    return resp["id"]


def youtube(video, m, privacy):
    return _retry(lambda: _youtube_once(video, m, privacy))


def _upload_binary(url, token, path):
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        r = requests.post(url, headers={
            "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)},
            data=f, timeout=900)
    r.raise_for_status()


def facebook(video, caption):
    page, tok = os.environ["META_PAGE_ID"], os.environ["META_PAGE_TOKEN"]
    r = requests.post(f"{G}/{page}/video_reels",
                      data={"upload_phase": "start", "access_token": tok}, timeout=60)
    r.raise_for_status()
    j = r.json()
    _upload_binary(j["upload_url"], tok, video)
    r = requests.post(f"{G}/{page}/video_reels", data={
        "upload_phase": "finish", "video_id": j["video_id"],
        "video_state": "PUBLISHED", "description": caption, "access_token": tok}, timeout=120)
    r.raise_for_status()
    return j["video_id"]


def instagram(video, caption):
    ig, tok = os.environ["IG_USER_ID"], os.environ["META_PAGE_TOKEN"]
    r = requests.post(f"{G}/{ig}/media", data={
        "media_type": "REELS", "upload_type": "resumable", "caption": caption,
        "share_to_feed": "true", "access_token": tok}, timeout=60)
    r.raise_for_status()
    j = r.json()
    cid = j["id"]
    _upload_binary(j.get("uri") or f"https://rupload.facebook.com/ig-api-upload/v21.0/{cid}", tok, video)
    for _ in range(40):  # up to ~6 minutes
        s = requests.get(f"{G}/{cid}", params={"fields": "status_code", "access_token": tok}, timeout=60).json()
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") == "ERROR":
            raise RuntimeError(f"Instagram processing error: {s}")
        time.sleep(10)
    else:
        raise RuntimeError("Instagram processing timeout")
    r = requests.post(f"{G}/{ig}/media_publish",
                      data={"creation_id": cid, "access_token": tok}, timeout=60)
    r.raise_for_status()
    return r.json().get("id")
