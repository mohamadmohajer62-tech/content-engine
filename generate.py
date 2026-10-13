import os, csv, re, sys, time, base64, requests

WP = "https://mohammadmohajer.ir"
AUTH = (os.environ["WP_USER"], os.environ["WP_APP_PASSWORD"])
SYSTEM = open("prompt.md", encoding="utf-8").read()
SYSTEM = re.sub(r"^- طول:.*$", "", SYSTEM, flags=re.M)
GAP = os.environ.get("GAPGPT_API_KEY", "").strip()
OR_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
IMG_MODEL = os.environ.get("IMAGE_MODEL", "").strip()
IMG_SIZE = os.environ.get("IMAGE_SIZE", "1536x1024").strip() or "1536x1024"
GAP_BASE = "https://api.gapgpt.app/v1"

# نشست اتصال به وردپرس: هدر مرورگرمانند و تلاش مجدد برای درخواست‌های خواندنی
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (compatible; ContentEngine/1.0; +https://mohammadmohajer.ir)"})
S.mount("https://", HTTPAdapter(max_retries=Retry(total=5, connect=5, read=4, backoff_factor=5,
                                                   status_forcelist=[502, 503, 504])))

# سبک ثابت تصاویر سایت (برای یکدست‌بودن همه‌ی مقاله‌ها)
IMG_STYLE = ("Minimal flat vector editorial illustration, calm navy blue and warm orange palette, "
             "soft rounded shapes, clean wide composition, no text, no letters, no numbers, "
             "no logos, no realistic human faces.")

try:
    _st = open("image-style.txt", encoding="utf-8").read().strip()
    if _st:
        IMG_STYLE = _st
except Exception:
    pass


def wp(method, url, tries=5, **kw):
    """درخواست به وردپرس با تلاش مجدد (برای کندی یا قطع لحظه‌ای هاست)."""
    kw["timeout"] = max(kw.get("timeout", 0), 90)
    last = None
    for i in range(tries):
        try:
            r = S.request(method, url, **kw)
            _ = r.content  # خواندن کامل پاسخ داخل همین try تا خطای زمان‌بر هم گرفته شود
            if r.status_code in (502, 503, 504, 524) and i < tries - 1:
                print("WP %s status %s, retry %d/%d" % (method, r.status_code, i + 1, tries))
                time.sleep(15 * (i + 1))
                continue
            return r
        except requests.exceptions.RequestException as e:
            last = e
            print("WP %s error %s, retry %d/%d" % (method, type(e).__name__, i + 1, tries))
            time.sleep(15 * (i + 1))
    raise last


def chat(url, key, model, user, max_tokens, system=None):
    body = {"model": model, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system or SYSTEM},
                         {"role": "user", "content": user}]}
    for attempt in range(3):
        r = requests.post(url, headers={"Authorization": "Bearer " + key}, json=body, timeout=300)
        if r.status_code == 429:
            print("[%s] rate-limited, waiting 40s" % model)
            time.sleep(40)
            continue
        if r.status_code != 200:
            print("[%s] status %s %s" % (model, r.status_code, r.text[:150]))
            return ""
        return r.json()["choices"][0]["message"].get("content") or ""
    return ""


def free_models():
    data = requests.get("https://openrouter.ai/api/v1/models", timeout=30).json()["data"]
    bad = ["code", "coder", "lyria", "clip", "safety", "guard", "embed", "audio", "image",
           "vision", "omni", "agent", "stealth"]
    out = []
    for m in data:
        p = m.get("pricing", {})
        try:
            free = float(p.get("prompt", "1")) == 0 and float(p.get("completion", "1")) == 0
        except Exception:
            free = False
        if free and not m["id"].startswith("openrouter/") and not any(b in m["id"].lower() for b in bad) \
                and (m.get("context_length") or 0) >= 16000:
            out.append(m["id"])
    pref = ["gemma", "llama", "qwen", "deepseek", "mistral", "gpt-oss"]
    out.sort(key=lambda i: (not any(k in i.lower() for k in pref), i))
    return out


def ask(user, max_tokens, system=None):
    if GAP:
        t = chat(GAP_BASE + "/chat/completions", GAP, MODEL, user, max_tokens, system)
        if len(t) > 50:
            print("[GapGPT]", MODEL, "OK")
            return t
        print("GapGPT failed, trying OpenRouter free models.")
    if not OR_KEY:
        sys.exit("هیچ کلیدی برای مدل پیدا نشد.")
    for m in free_models()[:6]:
        t = chat("https://openrouter.ai/api/v1/chat/completions", OR_KEY, m, user, max_tokens, system)
        if len(t) > 50:
            print("[%s] OK" % m)
            return t
    sys.exit("هیچ مدلی پاسخ نداد.")


def clean(t):
    t = re.sub(r"```(html)?", "", t).strip()
    t = re.sub(r"^#{2,4}\s*(.+)$", r"<h3>\1</h3>", t, flags=re.M)
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"</?strong>", "", t)
    return t.replace("\u06d5", "ه")


def grab(text, key):
    m = re.search(r"^%s\s*[:：]\s*(.+)$" % key, text, re.M)
    return m.group(1).strip() if m else ""


# ---------- تصویر ----------
def extract_image(j):
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


def plain(html, n=900):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()[:n]


ART_SYSTEM = ("You are an art director for a Persian business-strategy blog. "
              "You write precise image briefs in English for an AI image generator.")


def art_brief(title, context, cover=False):
    kind = ("a cover image for the whole article" if cover else "an illustration for one section of the article")
    q = ("Article title (Persian): %s\nText the image should illustrate (Persian): %s\n\n"
         "Write ONE paragraph (45-70 words, English) describing %s. "
         "Choose ONE concrete, specific scene that a small-business owner would recognise from daily work "
         "(a real place, real objects, a clear action), not an abstract symbol. "
         "Include: the main subject, 3-5 specific objects, the setting, the camera angle/composition and the lighting mood. "
         "The scene must feel Iranian: an everyday Iranian city setting (neighbourhood shops, offices, bazaar corners, cafes, workshops), "
         "people with natural Iranian appearance and modest everyday clothing, details like tea glasses or Persian-style interiors only where natural; "
         "avoid a generic Western stock-photo look. "
         "Avoid clichés (lightbulb, rocket, chess pieces, handshake, arrows, gears, puzzle pieces). "
         "The picture must contain no text, letters, numbers, logos or readable signs. "
         "Return only the paragraph." % (title, context, kind))
    out = ask(q, 400, ART_SYSTEM)
    out = re.sub(r"\s+", " ", out).strip().strip('"')
    return out if len(out) > 40 else ""


def make_image(prompt):
    if not (GAP and IMG_MODEL):
        return None
    full = IMG_STYLE + " " + prompt
    heads = {"Authorization": "Bearer " + GAP}
    attempts = []
    for size in (IMG_SIZE, None):
        body = {"model": IMG_MODEL, "prompt": full, "n": 1}
        if size:
            body["size"] = size
        attempts.append((GAP_BASE + "/images/generations", body))
    attempts.append((GAP_BASE + "/chat/completions",
                     {"model": IMG_MODEL, "messages": [{"role": "user", "content": "Generate an image: " + full}]}))
    for url, body in attempts:
        try:
            r = requests.post(url, headers=heads, json=body, timeout=300)
        except Exception as e:
            print("Image error:", type(e).__name__)
            continue
        if r.status_code != 200:
            print("Image status", r.status_code, url.split("/v1")[1], r.text[:120])
            continue
        img = extract_image(r.json())
        if img and len(img) > 1000:
            return img
        print("Image response had no image", url.split("/v1")[1])
    return None


MAX_W = 1200          # حداکثر عرض تصویر (پیکسل)
MAX_KB = 150          # سقف حجم هدف (کیلوبایت)


def compress(data):
    """تبدیل به WebP سبک: کوچک‌کردن ابعاد و کاهش تدریجی کیفیت تا رسیدن به سقف حجم."""
    try:
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(data))
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGB")
        if im.mode == "RGBA":
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[3])
            im = bg
        if im.width > MAX_W:
            im = im.resize((MAX_W, int(im.height * MAX_W / im.width)), Image.LANCZOS)
        out = data
        for q in (82, 74, 66, 58, 50):
            buf = io.BytesIO()
            im.save(buf, "WEBP", quality=q, method=6)
            out = buf.getvalue()
            if len(out) <= MAX_KB * 1024:
                break
        print("Image compressed: %d KB -> %d KB (%dx%d)" % (len(data) // 1024, len(out) // 1024, im.width, im.height))
        return out, im.width, im.height
    except Exception as e:
        print("Compression skipped:", type(e).__name__, str(e)[:100])
        return data, None, None


def upload_image(data, slug, alt):
    data, w, h = compress(data)
    if data[:2] == b"\xff\xd8":
        ext, mime = "jpg", "image/jpeg"
    elif data[:4] == b"RIFF":
        ext, mime = "webp", "image/webp"
    else:
        ext, mime = "png", "image/png"
    r = wp("POST", WP + "/wp-json/wp/v2/media", auth=AUTH, timeout=180, data=data,
                      headers={"Content-Disposition": 'attachment; filename="%s.%s"' % (slug, ext),
                               "Content-Type": mime})
    if r.status_code not in (200, 201):
        print("Media upload failed", r.status_code, r.text[:150])
        return None, None, None, None
    j = r.json()
    wp("POST", "%s/wp-json/wp/v2/media/%s" % (WP, j["id"]), auth=AUTH,
                  json={"alt_text": alt, "title": alt}, timeout=60)
    return j["id"], j.get("source_url"), w, h


# ---------- شروع ----------
try:
    r = wp("GET", WP + "/wp-json/wp/v2/users/me", auth=AUTH, timeout=45)
except Exception as e:
    sys.exit("اتصال به سایت برقرار نشد (%s). احتمالاً فایروال یا هاست جلوی GitHub را گرفته؛ چند دقیقه بعد دوباره امتحان کنید." % type(e).__name__)
print("WordPress:", r.status_code)
if r.status_code != 200:
    sys.exit("اتصال وردپرس درست نیست.")

with open("calendar.csv", encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    fields = reader.fieldnames
    rows = list(reader)
row = next((x for x in rows if x["status"].strip().lower() == "ready"), None)
if not row:
    sys.exit("ردیفی با وضعیت ready نیست.")
kw = row["primary_keyword"]
kw2 = row["secondary_keywords"].replace("|", "، ")
print("Topic:", row["topic"])

# درخواست ۱: طرح کلی
o = ask("""موضوع: %s
کلمه‌ی کلیدی اصلی: %s
کلمات فرعی: %s

برای این مقاله یک عنوان جذاب (شامل کلمه‌ی کلیدی)، یک slug انگلیسی کوتاه و ۶ بخش طراحی کن. بخش اول مقدمه و بخش آخر جمع‌بندی است.
عنوان بخش‌ها: کوتاه، روشن و جذاب، نه کلی؛ دو یا سه تا از آن‌ها شامل کلمه‌ی کلیدی یا مفهوم اصلی باشند. هر بخش وظیفه‌ی جدا داشته باشد.
دقیقاً در این قالب و بدون هیچ توضیح دیگر:
TITLE: ...
SLUG: ...
H1: مقدمه | هدف بخش در یک جمله
H2: عنوان بخش | هدف بخش در یک جمله
H3: ...
H4: ...
H5: ...
H6: جمع‌بندی | هدف بخش در یک جمله""" % (row["topic"], kw, kw2), 900)
title = grab(o, "TITLE") or row["topic"]
slug = re.sub(r"[^a-z0-9-]", "", grab(o, "SLUG").lower().replace(" ", "-"))[:60].strip("-") or ("article-" + row["id"])
heads = []
for h in re.findall(r"^H\d\s*[:：]\s*(.+)$", o, re.M):
    name, _, goal = h.partition("|")
    heads.append((name.strip(), goal.strip() or name.strip()))
if len(heads) < 5:
    print("Outline not parsed, using defaults.")
    heads = [("مقدمه", "مسئله را زنده کن"), ("موضوع دقیقاً چیست؟", "توضیح ساده"),
             ("چرا بیشتر مردم اشتباه می‌کنند؟", "نکته‌ای که کمتر دیده می‌شود"),
             ("یک نمونه‌ی فرضی", "مثال ملموس"), ("برنامه‌ی عملی قدم‌به‌قدم", "راهکار اجرایی"),
             ("جمع‌بندی", "جمع‌بندی کوتاه")]
print("Title:", title, "| slug:", slug, "| sections:", len(heads))

dup = wp("GET", WP + "/wp-json/wp/v2/posts", params={"slug": slug, "status": "any"}, auth=AUTH, timeout=30).json()
if isinstance(dup, list) and dup:
    sys.exit("مقاله‌ای با این slug قبلاً هست: " + slug)

# نوشتن بخش‌ها
QUOTE_SECTION = 2
parts = []
names = " | ".join(n for n, _ in heads)
for i, (name, goal) in enumerate(heads):
    prev = re.sub(r"<[^>]+>", " ", " ".join(parts))[-400:]
    if i == 0:
        extra = "این بخش مقدمه است؛ مسئله را زنده کن و خواننده را وارد بحث کن."
    elif i == len(heads) - 1:
        extra = "این بخش جمع‌بندی است؛ کوتاه جمع‌بندی کن و با یک سؤال برای خواننده تمام کن."
    elif i == QUOTE_SECTION:
        extra = ("یک جمله‌ی کلیدی و ماندگار از دیدگاه خودت (نه نقل‌قول از شخص یا کتاب دیگر) را "
                 "در یک بلوک <blockquote><p>...</p></blockquote> بیاور.")
    else:
        extra = "اگر بخش بلند شد، یک یا دو زیرعنوان h3 بگذار."
    body = clean(ask("""مقاله: «%s» | کلمه‌ی کلیدی: %s
فهرست بخش‌ها: %s

حالا فقط بخش «%s» را بنویس. هدف این بخش: %s. %s
حدود ۲۸۰ تا ۳۵۰ کلمه بنویس (کوتاه‌تر نباشد)، با توضیح کافی، مثال یا جزئیات.
متن را پررنگ (bold) نکن.
فقط HTML ساده (p, ul, li, h3, blockquote). تیتر h2 نگذار و مطالب بخش‌های دیگر را تکرار نکن.
پایان متن قبلی (تکرارش نکن): %s""" % (title, kw, names, name, goal, extra, prev), 1800))
    parts.append(("" if i == 0 else "<h2>%s</h2>\n" % name) + body + "\n")
words = len(re.sub(r"<[^>]+>", " ", "\n".join(parts)).split())
print("Word count:", words, "(کمتر از ۱۲۰۰ است!)" if words < 1200 else "")

# درخواست آخر: سئو و پرامپت تصاویر
h2name = heads[1][0] if len(heads) > 1 else heads[0][0]
h4name = heads[3][0] if len(heads) > 3 else heads[-1][0]
s = ask("""برای مقاله‌ی «%s» با کلمه‌ی کلیدی «%s» دقیقاً در این قالب بنویس، هر مورد در یک خط:
META_TITLE: حداکثر ۶۰ کاراکتر، بدون کلیشه
META_DESC: ۱۴۰ تا ۱۶۰ کاراکتر، جذاب و بدون عبارت کلیشه‌ای
EXCERPT: ۲ جمله
TAGS: ۴ تا ۵ برچسب جداشده با علامت |
ALT1: متن جایگزین تصویر شاخص به فارسی، یک جمله‌ی کوتاه شامل کلمه‌ی کلیدی
IMG1: یک جمله‌ی انگلیسی؛ استعاره‌ی تصویری ساده برای موضوع کلی مقاله، بدون متن و حرف
ALT2: متن جایگزین تصویر دوم به فارسی (مربوط به بخش «%s»)
IMG2: یک جمله‌ی انگلیسی؛ استعاره‌ی تصویری ساده برای مفهوم بخش «%s»
ALT3: متن جایگزین تصویر سوم به فارسی (مربوط به بخش «%s»)
IMG3: یک جمله‌ی انگلیسی؛ استعاره‌ی تصویری ساده برای مفهوم بخش «%s»
Q1: سؤال واقعی یک مدیر کسب‌وکار
A1: پاسخ ۲ تا ۳ جمله
Q2: ...
A2: ...
Q3: ...
A3: ...""" % (title, kw, h2name, h2name, h4name, h4name), 1800)
meta_title = grab(s, "META_TITLE")[:60] or title[:60]
meta_desc = grab(s, "META_DESC")[:160]
excerpt = grab(s, "EXCERPT")
tags = [x.strip() for x in grab(s, "TAGS").split("|") if x.strip()] or [x.strip() for x in kw2.split("،") if x.strip()]
faq = [(grab(s, "Q%d" % i), grab(s, "A%d" % i)) for i in (1, 2, 3)]
faq = [(q, a) for q, a in faq if q and a]

cat_ids = []
try:
    cr = wp("GET", WP + "/wp-json/wp/v2/categories", tries=3, auth=AUTH, timeout=60,
            params={"search": row["category"].strip(), "per_page": 20, "_fields": "id,name"})
    cats = cr.json()
    cat_ids = [c["id"] for c in cats if c.get("name", "").strip() == row["category"].strip()]
except Exception as e:
    print("Category lookup failed (%s); continuing without category." % type(e).__name__)
print("Category ids:", cat_ids)

tag_ids = []
for tg in tags[:5]:
    try:
        tr = wp("POST", WP + "/wp-json/wp/v2/tags", tries=3, auth=AUTH, json={"name": tg}, timeout=60)
        if tr.status_code in (200, 201):
            tag_ids.append(tr.json()["id"])
        elif tr.status_code == 400 and "term_id" in tr.text:
            tag_ids.append(tr.json()["data"]["term_id"])
    except Exception as e:
        print("Tag '%s' failed (%s); skipping." % (tg, type(e).__name__))

# تصاویر: ۱ شاخص + ۲ داخل مقاله (اختیاری)
featured_id = None
if IMG_MODEL and GAP:
    specs = [(grab(s, "IMG1"), grab(s, "ALT1") or title, "cover"),
             (grab(s, "IMG2"), grab(s, "ALT2") or title, "img2"),
             (grab(s, "IMG3"), grab(s, "ALT3") or title, "img3")]
    inline_slots = [1, 3]
    ctxs = [title + ". " + plain(parts[0]), plain(parts[1]), plain(parts[min(3, len(parts) - 1)])]
    for n, (idea, alt, tag) in enumerate(specs):
        try:
            brief = art_brief(title, ctxs[n], cover=(n == 0))
        except SystemExit:
            brief = ""
        idea = brief or idea or "a simple visual metaphor for growing a small business"
        print("Image %d brief: %s" % (n + 1, idea[:160]))
        data = make_image(idea)
        if not data:
            print("Image %d failed; skipping." % (n + 1))
            continue
        try:
            mid, url, iw, ih = upload_image(data, "%s-%s" % (slug, tag), alt)
        except Exception as e:
            print("Image %d upload failed (%s); skipping." % (n + 1, type(e).__name__))
            continue
        print("Image %d uploaded: id=%s" % (n + 1, mid))
        if not mid:
            continue
        if n == 0:
            featured_id = mid
        elif url and n <= len(inline_slots) and inline_slots[n - 1] < len(parts):
            dims = (' width="%s" height="%s"' % (iw, ih)) if iw else ""
            fig = '<figure class="mm-fig"><img src="%s" alt="%s"%s loading="lazy" decoding="async" /></figure>\n' % (url, alt, dims)
            parts[inline_slots[n - 1]] += fig
else:
    print("IMAGE_MODEL not set: skipping images.")

html = "\n".join(parts)
if faq:
    html += "\n<h2>سوالات متداول</h2>\n" + "".join("<h3>%s</h3>\n<p>%s</p>\n" % (q, a) for q, a in faq)

focus = ", ".join([kw] + [x.strip() for x in kw2.split("،") if x.strip()][:2])
wrapped = '<div class="mm-article">' + html + "</div>"
meta = {}
meta["rank_math_title"] = meta_title
meta["rank_math_description"] = meta_desc
meta["rank_math_focus_keyword"] = focus
payload = {}
payload["title"] = title
payload["slug"] = slug
payload["content"] = wrapped
payload["excerpt"] = excerpt
payload["status"] = "draft"
payload["categories"] = cat_ids
payload["tags"] = tag_ids
payload["meta"] = meta
if featured_id:
    payload["featured_media"] = featured_id
try:
    post = wp("POST", WP + "/wp-json/wp/v2/posts", tries=1, auth=AUTH, timeout=120, json=payload)
except requests.exceptions.RequestException as e:
    # ممکن است پست ساخته شده ولی پاسخ نرسیده باشد؛ قبل از هر تلاش دیگر با slug بررسی می‌کنیم
    print("Create post error %s; checking whether it was created..." % type(e).__name__)
    time.sleep(20)
    found = wp("GET", WP + "/wp-json/wp/v2/posts", params={"slug": slug, "status": "any"}, auth=AUTH, timeout=60).json()
    if isinstance(found, list) and found:
        class _P:
            status_code = 201
            def json(self):
                return found[0]
        post = _P()
    else:
        post = wp("POST", WP + "/wp-json/wp/v2/posts", tries=2, auth=AUTH, timeout=120, json=payload)
print("Create post:", post.status_code)
if post.status_code not in (200, 201):
    sys.exit(post.text[:300])
pid = post.json()["id"]
print("Draft ID:", pid, "| edit:", "%s/wp-admin/post.php?post=%s&action=edit" % (WP, pid))

try:
    chk = wp("GET", "%s/wp-json/wp/v2/posts/%s" % (WP, pid), tries=2, params={"context": "edit"}, auth=AUTH, timeout=60).json()
    m = chk.get("meta") or {}
    print("Rank Math saved:", bool(m.get("rank_math_title")), "| focus:", m.get("rank_math_focus_keyword"))
except Exception as e:
    print("Rank Math check skipped (%s)." % type(e).__name__)
print("META_TITLE:", meta_title)
print("META_DESC:", meta_desc)

if "wp_id" not in fields:
    fields.append("wp_id")
row["status"] = "draft"
row["wp_id"] = str(pid)
with open("calendar.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)
