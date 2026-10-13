import os, json, re, time, random, requests

MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
MIN_GAP = float(os.getenv("LLM_MIN_GAP", "2"))  # do calls ke beech kam az kam itne second
_last = 0.0


class LLMError(RuntimeError):
    """Gemini call kisi bhi wajah se nahi chali (asli wajah message mein)."""


def ask_json(prompt, system="", temperature=0.8, retries=6):
    global _last
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    headers = {"x-goog-api-key": os.environ["GEMINI_API_KEY"]}
    last_err = ""
    for i in range(retries):
        gap = MIN_GAP - (time.time() - _last)
        if gap > 0:
            time.sleep(gap)
        _last = time.time()
        delay = 0.0
        try:
            r = requests.post(url, headers=headers, json=body, timeout=120)
            if r.status_code in (429, 500, 502, 503, 504):
                # quota/overload: intezaar karke dobara (Retry-After ho to wahi)
                last_err = f"HTTP {r.status_code}: {r.text[:200]}"
                ra = r.headers.get("Retry-After", "")
                delay = float(ra) if ra.replace(".", "", 1).isdigit() else min(60, 8 * 2 ** i)
                delay += random.uniform(0, 4)  # 3 jobs ek saath na takrayen
            elif r.status_code >= 400:
                # galat key / galat request: dobara koshish bekar
                raise LLMError(f"HTTP {r.status_code}: {r.text[:300]}")
            else:
                text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
                return json.loads(text)
        except LLMError:
            raise
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:200]}"
            delay = 3 + random.uniform(0, 3)
        print(f"LLM retry {i + 1}/{retries} ({last_err}); {delay:.0f}s ruk raha hoon")
        if i < retries - 1:
            time.sleep(delay)
    raise LLMError("Gemini call failed: " + last_err)
