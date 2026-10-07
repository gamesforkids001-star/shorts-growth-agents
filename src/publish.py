import os, time, requests

G = "https://graph.facebook.com/v21.0"


def youtube(video, m, privacy):
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
