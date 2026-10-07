import os, json, re, time, requests

MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")


def ask_json(prompt, system="", temperature=0.8, retries=3):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    headers = {"x-goog-api-key": os.environ["GEMINI_API_KEY"]}
    for i in range(retries):
        try:
            r = requests.post(url, headers=headers, json=body, timeout=120)
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
            return json.loads(text)
        except Exception as e:
            print("LLM retry", i + 1, e)
            time.sleep(5 * (i + 1))
    raise RuntimeError("Gemini call failed")
