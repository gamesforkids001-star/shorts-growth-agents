import os, json, re, time, random, requests

MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
MIN_GAP = float(os.getenv("LLM_MIN_GAP", "2"))  # do calls ke beech kam az kam itne second
_last = 0.0
BUDGET = float(os.getenv("LLM_BUDGET", "240"))  # ek job mein retry ke intezaar ka kul waqt (second)
_waited = 0.0
_daily_dead = False  # roz ka quota khatam ho gaya to baqi calls foran fail (intezaar bekar)


class LLMError(RuntimeError):
    """Gemini call kisi bhi wajah se nahi chali (asli wajah message mein)."""


def ask_json(prompt, system="", temperature=0.8, retries=6):
    global _last, _waited, _daily_dead
    if _daily_dead:
        raise LLMError("Gemini roz ka quota khatam (PerDay): dobara kal koshish karo")
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
                last_err = f"HTTP {r.status_code}: {r.text[:700]}"
                if r.status_code == 429 and re.search(r"per ?day", r.text, re.I):
                    _daily_dead = True
                    raise LLMError("Gemini roz ka quota khatam (PerDay): " + r.text[:500])
                ra = r.headers.get("Retry-After", "")
                m = re.search(r'"retryDelay":\s*"(\d+(?:\.\d+)?)s"', r.text)
                if ra.replace(".", "", 1).isdigit():
                    delay = float(ra)
                elif m:
                    delay = min(60.0, float(m.group(1)) + 1)
                else:
                    delay = min(60, 8 * 2 ** i)
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
        print(f"LLM retry {i + 1}/{retries} ({last_err[:300]}); {delay:.0f}s ruk raha hoon")
        if i < retries - 1:
            if _waited + delay > BUDGET:
                raise LLMError("Gemini intezaar ki hadd poori (job latakne se bachne ke liye): " + last_err[:300])
            _waited += delay
            time.sleep(delay)
    raise LLMError("Gemini call failed: " + last_err)
