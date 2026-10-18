import os, time, json, subprocess, requests

G = "https://graph.facebook.com/v21.0"          # Facebook Page
GI = "https://graph.instagram.com/v21.0"        # Instagram (Instagram Login token)


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


def _ok(r, what):
    """HTTP error ho to Meta ka asli error text dikhao (sirf 400 nahi)."""
    if r.status_code >= 400:
        raise RuntimeError(f"{what}: HTTP {r.status_code} {r.text[:500]}")
    return r


def _upload_binary(url, token, path, what="upload"):
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        r = requests.post(url, headers={
            "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)},
            data=f, timeout=900)
    _ok(r, what)


def facebook(video, caption):
    page, tok = os.environ["FB_PAGE_ID"], os.environ["FB_PAGE_ACCESS_TOKEN"]
    r = _ok(requests.post(f"{G}/{page}/video_reels",
                          data={"upload_phase": "start", "access_token": tok}, timeout=60), "Facebook start")
    j = r.json()
    _upload_binary(j["upload_url"], tok, video, "Facebook upload")
    _ok(requests.post(f"{G}/{page}/video_reels", data={
        "upload_phase": "finish", "video_id": j["video_id"],
        "video_state": "PUBLISHED", "description": caption, "access_token": tok}, timeout=120),
        "Facebook finish")
    return j["video_id"]


UA = {"User-Agent": "Mozilla/5.0 (compatible; shorts-growth-agents/1.0)"}


def _host_litterbox(path):
    with open(path, "rb") as f:
        r = requests.post("https://litterbox.catbox.moe/resources/internals/api.php",
                          data={"reqtype": "fileupload", "time": "1h"},
                          files={"fileToUpload": f}, headers=UA, timeout=300)
    return r.status_code, r.text.strip()


def _host_catbox(path):
    with open(path, "rb") as f:
        r = requests.post("https://catbox.moe/user/api.php",
                          data={"reqtype": "fileupload"},
                          files={"fileToUpload": f}, headers=UA, timeout=300)
    return r.status_code, r.text.strip()


def _host_uguu(path):
    with open(path, "rb") as f:
        r = requests.post("https://uguu.se/upload", files={"files[]": f},
                          headers=UA, timeout=300)
    try:
        return r.status_code, r.json()["files"][0]["url"]
    except Exception:
        return r.status_code, r.text.strip()


def _host_tmpfiles(path):
    with open(path, "rb") as f:
        r = requests.post("https://tmpfiles.org/api/v1/upload", files={"file": f},
                          headers=UA, timeout=300)
    try:
        u = r.json()["data"]["url"]
        return r.status_code, u.replace("tmpfiles.org/", "tmpfiles.org/dl/", 1).replace("http://", "https://")
    except Exception:
        return r.status_code, r.text.strip()


def _host_0x0(path):
    with open(path, "rb") as f:
        r = requests.post("https://0x0.st", files={"file": f},
                          headers=UA, timeout=300)
    return r.status_code, r.text.strip()


def _link_works(url):
    """Link sach mein video de raha hai ya nahi (Instagram ke liye zaroori)."""
    try:
        r = requests.get(url, headers=UA, stream=True, timeout=60, allow_redirects=True)
        ctype = r.headers.get("Content-Type", "")
        r.close()
        return r.status_code == 200 and ("video" in ctype or "octet-stream" in ctype)
    except Exception:
        return False


def _public_url(path):
    """Instagram ko video_url chahiye: video ko public link par rakho.
    Ek host fail ho to agla try hota hai (litterbox 17 Oct ko 412 de raha tha)."""
    hosts = [("litterbox", _host_litterbox), ("catbox", _host_catbox),
             ("uguu", _host_uguu), ("tmpfiles", _host_tmpfiles), ("0x0", _host_0x0)]
    errors = []
    for name, fn in hosts:
        try:
            code, url = fn(path)
            if code == 200 and url.startswith("https://") and _link_works(url):
                print(f"public link bana ({name}): {url}")
                return url
            errors.append(f"{name}: HTTP {code} {url[:80]}")
        except Exception as e:
            errors.append(f"{name}: {str(e)[:80]}")
        print("public link host fail:", errors[-1])
    raise RuntimeError("public link nahi bana, sab hosts fail: " + " | ".join(errors))


def instagram(video, caption):
    ig, tok = os.environ["IG_USER_ID"], os.environ["IG_ACCESS_TOKEN"]
    base = {"media_type": "REELS", "caption": caption,
            "share_to_feed": "true", "access_token": tok}
    try:
        r = _ok(requests.post(f"{GI}/{ig}/media", data={**base, "upload_type": "resumable"},
                              timeout=60), "Instagram container")
        j = r.json()
        cid = j["id"]
        _upload_binary(j.get("uri") or f"https://rupload.facebook.com/ig-api-upload/v21.0/{cid}",
                       tok, video, "Instagram upload")
    except RuntimeError as e:
        # 17 Oct: "video_url is required" aaya, yani resumable is account par kaam nahi karta
        if "video_url" not in str(e):
            raise
        print("Instagram resumable kaam nahi kiya, video_url tareeqa:", str(e)[:150])
        url = _public_url(video)
        r = _ok(requests.post(f"{GI}/{ig}/media", data={**base, "video_url": url},
                              timeout=60), "Instagram container (video_url)")
        cid = r.json()["id"]
    for _ in range(40):  # up to ~6 minutes
        s = requests.get(f"{GI}/{cid}", params={"fields": "status_code", "access_token": tok},
                         timeout=60).json()
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") == "ERROR":
            raise RuntimeError(f"Instagram processing error: {s}")
        time.sleep(10)
    else:
        raise RuntimeError("Instagram processing timeout")
    r = _ok(requests.post(f"{GI}/{ig}/media_publish",
                          data={"creation_id": cid, "access_token": tok}, timeout=60), "Instagram publish")
    return r.json().get("id")
