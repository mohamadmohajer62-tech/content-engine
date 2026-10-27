"""
آزمایشگاه تصویر: مقایسه‌ی مدل‌های گپ‌جی‌پی‌تی برای تصویر شاخص، و ساخت اینفوگرافیک از متن مقاله.
MODE=models      : فهرست مدل‌های تصویری حساب شما
MODE=cover       : یک تصویر شاخص برای هر مدل (برای مقایسه)
MODE=infographic : اینفوگرافیک با HTML (متن فارسی بی‌نقص) و، اگر مدل بدهید، نسخه‌ی هوش مصنوعی برای مقایسه
"""
import os, re, sys, time
import requests
import generate as g
import brand_render as b

MODE = os.environ.get("MODE", "models").strip()
POST_ID = os.environ.get("POST_ID", "").strip()
TITLE = os.environ.get("TITLE", "").strip()
KEYWORD = os.environ.get("KEYWORD", "").strip()
MODELS = [m.strip() for m in os.environ.get("MODELS", "").split(",") if m.strip()]
TILES = int(os.environ.get("TILES", "6") or 6)
FMT = os.environ.get("FMT", "post").strip() or "post"
os.makedirs("out", exist_ok=True)
HEADS = {"Authorization": "Bearer " + g.GAP}


def safe(m):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", m)


def ext_of(data):
    return "png" if data[:4] == b"\x89PNG" else ("webp" if data[:4] == b"RIFF" else "jpg")


def list_models():
    r = requests.get(g.GAP_BASE + "/models", headers=HEADS, timeout=60)
    print("HTTP", r.status_code)
    if r.status_code != 200:
        print(r.text[:300])
        sys.exit(1)
    ids = sorted({m.get("id", "") for m in r.json().get("data", []) if m.get("id")})
    pat = re.compile(r"image|flux|banana|imagen|dall|seedream|ideogram|recraft|qwen|kolors|midjourney|stable|sdxl|gemini.*(flash|pro).*img", re.I)
    img = [i for i in ids if pat.search(i)]
    print("Total models: %d | image-like: %d" % (len(ids), len(img)))
    print("\n".join(img))
    open("out/models.txt", "w", encoding="utf-8").write("\n".join(img))


def raw_image(prompt, model, size):
    """درخواست تصویر بدون افزودن سبک عکس مستند (برای اینفوگرافیک)."""
    attempts = []
    for sz in (size, None):
        body = {"model": model, "prompt": prompt, "n": 1}
        if sz:
            body["size"] = sz
        attempts.append((g.GAP_BASE + "/images/generations", body))
    attempts.append((g.GAP_BASE + "/chat/completions", {"model": model, "messages": [{"role": "user", "content": "Generate an image: " + prompt}]}))
    for url, body in attempts:
        try:
            r = requests.post(url, headers=HEADS, json=body, timeout=300)
        except Exception as e:
            print("Image error [%s]: %s" % (model, type(e).__name__))
            continue
        if r.status_code != 200:
            print("Image status [%s] %s %s" % (model, r.status_code, r.text[:200]))
            continue
        img = g.extract_image(r.json())
        if img:
            return img
    return None


def load_article():
    if POST_ID:
        a = b.fetch_article(g, POST_ID)
        if TITLE:
            a["title"] = TITLE
        return a
    if not TITLE:
        sys.exit("شماره‌ی مقاله (post_id) یا عنوان را وارد کنید.")
    return {"title": TITLE, "text": KEYWORD, "image": None, "link": ""}


def cover_lab():
    art = load_article()
    if not MODELS:
        sys.exit("حداقل یک مدل وارد کنید (با کاما جدا کنید). فهرست مدل‌ها را با MODE=models ببینید.")
    context = (art["text"] or KEYWORD)[:900]
    brief = g.art_brief(art["title"], context, KEYWORD and ("مضمون: " + KEYWORD) or "")
    print("Brief:", brief[:300])
    rows = []
    for m in MODELS:
        t0 = time.time()
        data = g.make_image(brief, m)
        dt = time.time() - t0
        if data:
            path = "out/cover-%s.%s" % (safe(m), ext_of(data))
            open(path, "wb").write(data)
            b.send_photo(g, path, "تصویر شاخص | مدل: %s | %.0f ثانیه\n%s" % (m, dt, art["title"]))
            rows.append((m, "OK", "%.0fs" % dt, len(data) // 1024))
        else:
            rows.append((m, "FAILED", "%.0fs" % dt, 0))
    print("\n== نتیجه ==")
    for r in rows:
        print("%-40s %-7s %-6s %s KB" % r)
    print("هزینه‌ی هر مدل را در پنل گپ‌جی‌پی‌تی (مصرف اعتبار پیش و پس از این اجرا) مقایسه کنید.")


def infographic_lab():
    art = load_article()
    n = TILES if TILES in (4, 6, 8) else 6
    j = b.ask_json(g, (
        "عنوان مقاله: %s\n\nمتن مقاله:\n%s\n\n"
        "از همین متن یک اینفوگرافیک بساز: title (حداکثر ۵۰ نویسه) و دقیقاً %d آیتم کاربردی، "
        "هر آیتم h (تیتر ۱۵ تا ۳۰ نویسه) و t (توضیح ۴۵ تا ۹۰ نویسه). فقط از محتوای همین متن؛ فارسی روان و ساده.\n"
        'خروجی: {"title":"...","items":[{"h":"...","t":"..."}]}' % (art["title"], art["text"][:6000] or art["title"]), 1200))
    if not j or not isinstance(j.get("items"), list) or len(j["items"]) < 3:
        sys.exit("مدل زبانی ساختار اینفوگرافیک را برنگرداند؛ دوباره اجرا کنید.")
    title, items = str(j.get("title") or art["title"])[:70], j["items"][:n]
    print("Infographic:", title, "|", len(items), "items")
    path = b.infographic(title, items, "out/infographic-html-%s.png" % FMT, FMT)
    b.send_photo(g, path, "اینفوگرافیک (HTML، هویت سایت) | %s\n%s" % (FMT, art["title"]))

    size = "1024x1280" if FMT == "post" else "1024x1792"
    for m in MODELS:
        lines = "\n".join("%d. %s — %s" % (i + 1, it.get("h", ""), it.get("t", "")) for i, it in enumerate(items))
        prompt = ("Design a clean modern infographic, vertical, on a cream background (#F6F1E6) using deep green (#386641) and terracotta orange (#CC6A45). "
                  "Right-to-left Persian typography, large readable letters, rounded cards in a 2-column grid, each card with a numbered circle. "
                  "All Persian text must be spelled EXACTLY as given, with correct connected letters; no extra words.\n"
                  "Title: %s\nCards:\n%s" % (title, lines))
        t0 = time.time()
        data = raw_image(prompt, m, size)
        dt = time.time() - t0
        if data:
            p = "out/infographic-ai-%s.%s" % (safe(m), ext_of(data))
            open(p, "wb").write(data)
            b.send_photo(g, p, "اینفوگرافیک هوش مصنوعی | مدل: %s | %.0f ثانیه (املای فارسی را بررسی کنید)" % (m, dt))
        else:
            print("Model %s produced no image." % m)


if MODE == "models":
    list_models()
elif MODE == "cover":
    cover_lab()
elif MODE == "infographic":
    infographic_lab()
else:
    sys.exit("MODE نامعتبر است: models | cover | infographic")
