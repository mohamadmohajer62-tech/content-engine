import os, re, base64, sys, requests

KEY = os.environ.get("GAPGPT_API_KEY", "").strip()
MODEL = os.environ.get("MODEL", "").strip()
BASE = "https://api.gapgpt.app/v1"
if not KEY or not MODEL:
    sys.exit("کلید یا نام مدل خالی است.")
PROMPT = ("Minimal flat vector editorial illustration, calm navy blue and warm orange palette, "
          "wide composition, no text, no letters. A small shop owner standing before a simple path "
          "of three stepping stones leading to a glowing door.")

def extract(j):
    try:
        d = j["data"][0]
        if d.get("b64_json"):
            return base64.b64decode(d["b64_json"])
        if d.get("url"):
            return requests.get(d["url"], timeout=120).content
    except Exception:
        pass
    try:
        msg = j["choices"][0]["message"]
    except Exception:
        return None
    cands = []
    for im in (msg.get("images") or []):
        u = im.get("image_url") if isinstance(im, dict) else im
        cands.append(u.get("url") if isinstance(u, dict) else u)
    c = msg.get("content")
    if isinstance(c, list):
        for p in c:
            if isinstance(p, dict) and p.get("image_url"):
                u = p["image_url"]
                cands.append(u.get("url") if isinstance(u, dict) else u)
    elif isinstance(c, str):
        cands += re.findall(r"data:image/[a-zA-Z+]+;base64,[A-Za-z0-9+/=]+", c)
        cands += re.findall(r"!\[[^\]]*\]\((https?://[^)\s]+)\)", c)
        cands += re.findall(r"(https?://\S+?\.(?:png|jpg|jpeg|webp))", c)
    for u in cands:
        if not u:
            continue
        if u.startswith("data:"):
            return base64.b64decode(u.split("base64,", 1)[1])
        if u.startswith("http"):
            return requests.get(u, timeout=120).content
    return None

tries = [
    ("images + size", BASE + "/images/generations", {"model": MODEL, "prompt": PROMPT, "n": 1, "size": "1536x1024"}),
    ("images", BASE + "/images/generations", {"model": MODEL, "prompt": PROMPT, "n": 1}),
    ("chat", BASE + "/chat/completions", {"model": MODEL, "messages": [{"role": "user", "content": "Generate an image: " + PROMPT}]}),
]
for name, url, body in tries:
    try:
        r = requests.post(url, headers={"Authorization": "Bearer " + KEY}, json=body, timeout=300)
    except Exception as e:
        print("[%s] error %s" % (name, type(e).__name__))
        continue
    print("[%s] status %s" % (name, r.status_code))
    if r.status_code != 200:
        print("   ", r.text[:200])
        continue
    img = extract(r.json())
    if img and len(img) > 1000:
        ext = "jpg" if img[:2] == b"\xff\xd8" else ("webp" if img[:4] == b"RIFF" else "png")
        open("test_out." + ext, "wb").write(img)
        print("RESULT: IMAGE OK via '%s' | %d bytes | saved test_out.%s" % (name, len(img), ext))
        sys.exit(0)
    print("   200 but no image found. keys:", list(r.json().keys()))
sys.exit("RESULT: هیچ روشی تصویر نداد.")
