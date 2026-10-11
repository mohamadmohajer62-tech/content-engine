import os, sys, requests

KEY = os.environ.get("GAPGPT_API_KEY", "").strip()
if not KEY:
    sys.exit("کلید خالی است.")
r = requests.get("https://api.gapgpt.app/v1/models", headers={"Authorization": "Bearer " + KEY}, timeout=60)
print("status:", r.status_code)
if r.status_code != 200:
    sys.exit(r.text[:300])
data = r.json().get("data", [])
ids = sorted(m.get("id", "") for m in data)
print("TOTAL models:", len(ids))
words = ["image", "banana", "qwen", "flux", "dall", "imagen", "midjourney", "seedream", "gemini", "gpt-image"]
hits = [i for i in ids if any(w in i.lower() for w in words)]
print("--- image-related candidates (%d) ---" % len(hits))
for i in hits:
    print(i)
if not hits:
    print("--- no match; first 80 models ---")
    for i in ids[:80]:
        print(i)
