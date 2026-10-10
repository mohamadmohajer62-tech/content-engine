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

def chat(url, key, model, user, max_tokens):
    body = {"model": model, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": user}]}
    for attempt in range(3):
        r = requests.post(url, headers={"Authorization": f"Bearer {key}"}, json=body, timeout=300)
        if r.status_code == 429:
            print(f"[{model}] rate-limited, waiting 40s"); time.sleep(40); continue
        if r.status_code != 200:
            print(f"[{model}] status {r.status_code} {r.text[:150]}"); return ""
        return r.json()["choices"][0]["message"].get("content") or ""
    return ""

def free_models():
    data = requests.get("https://openrouter.ai/api/v1/models", timeout=30).json()["data"]
    bad = ["code", "coder", "lyria", "clip", "safety", "guard", "embed", "audio", "image", "vision", "omni", "agent", "stealth"]
    out = []
    for m in data:
        p = m.get("pricing", {})
        try: free = float(p.get("prompt", "1")) == 0 and float(p.get("completion", "1")) == 0
        except Exception: free = False
        if free and not m["id"].startswith("openrouter/") and not any(b in m["id"].lower() for b in bad) and (m.get("context_length") or 0) >= 16000:
            out.append(m["id"])
    out.sort(key=lambda i: (not any(k in i.lower() for k in ["gemma", "llama", "qwen", "deepseek", "mistral", "gpt-oss"]), i))
    return out

def ask(user, max_tokens):
    if GAP:
        t = chat("https://api.gapgpt.app/v1/chat/completions", GAP, MODEL, user, max_tokens)
        if len(t) > 50: print("[GapGPT]", MODEL, "OK"); return t
        print("GapGPT failed, trying OpenRouter free models.")
    if not OR_KEY:
        sys.exit("هیچ کلیدی برای مدل پیدا نشد.")
    for m in free_models()[:6]:
        t = chat("https://openrouter.ai/api/v1/chat/completions", OR_KEY, m, user, max_tokens)
        if len(t) > 50: print(f"[{m}] OK"); return t
    sys.exit("هیچ مدلی پاسخ نداد.")

def clean(t):
    t = re.sub(r"```(html)?", "", t).strip()
    t = re.sub(r"^#{2,4}\s*(.+)$", r"<h3>\1</h3>", t, flags=re.M)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    return t.replace("\u06d5", "ه")

def grab(text, key):
    m = re.search(rf"^{key}\s*[:：]\s*(.+)$", text, re.M)
    return m.group(1).strip() if m else ""

def make_image(prompt):
    if not (GAP and IMG_MODEL):
        return None
    for size in (IMG_SIZE, None):
        body = {"model": IMG_MODEL, "prompt": prompt, "n": 1}
        if size: body["size"] = size
        try:
            r = requests.post("https://api.gapgpt.app/v1/images/generations",
                              headers={"Authorization": f"Bearer {GAP}"}, json=body, timeout=300)
        except Exception as e:
            print("Image error:", type(e).__name__); return None
        if r.status_code == 200:
            d = r.json()["data"][0]
            if d.get("b64_json"): return base64.b64decode(d["b64_json"])
            if d.get("url"): return requests.get(d["url"], timeout=120).content
            return None
        print("Image status", r.status_code, r.text[:150])
    return None

def upload_image(data, slug, alt):
    if data[:2] == b"\xff\xd8": ext, mime = "jpg", "image/jpeg"
    elif data[:4] == b"RIFF": ext, mime = "webp", "image/webp"
    else: ext, mime = "png", "image/png"
    r = requests.post(f"{WP}/wp-json/wp/v2/media", auth=AUTH, timeout=180, data=data,
                      headers={"Content-Disposition": f'attachment; filename="{slug}.{ext}"', "Content-Type": mime})
    if r.status_code not in (200, 201):
        print("Media upload failed", r.status_code, r.text[:150]); return None
    mid = r.json()["id"]
    requests.post(f"{WP}/wp-json/wp/v2/media/{mid}", auth=AUTH, json={"alt_text": alt, "title": alt}, timeout=60)
    return mid

r = requests.get(f"{WP}/wp-json/wp/v2/users/me", auth=AUTH, timeout=30)
print("WordPress:", r.status_code)
if r.status_code != 200: sys.exit("اتصال وردپرس درست نیست.")

with open("calendar.csv", encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f); fields = reader.fieldnames; rows = list(reader)
row = next((x for x in rows if x["status"].strip().lower() == "ready"), None)
if not row: sys.exit("ردیفی با وضعیت ready نیست.")
kw = row["primary_keyword"]
kw2 = row["secondary_keywords"].replace("|", "، ")
print("Topic:", row["topic"])

# درخواست ۱: طرح کلی
o = ask(f"""موضوع: {row['topic']}
کلمه‌ی کلیدی اصلی: {kw}
کلمات فرعی: {kw2}

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
H6: جمع‌بندی | هدف بخش در یک جمله""", 900)
title = grab(o, "TITLE") or row["topic"]
slug = re.sub(r"[^a-z0-9-]", "", grab(o, "SLUG").lower().replace(" ", "-"))[:60].strip("-") or f"article-{row['id']}"
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

dup = requests.get(f"{WP}/wp-json/wp/v2/posts", params={"slug": slug, "status": "any"}, auth=AUTH, timeout=30).json()
if isinstance(dup, list) and dup: sys.exit("مقاله‌ای با این slug قبلاً هست: " + slug)

# نوشتن بخش‌ها
parts = []
names = " | ".join(n for n, _ in heads)
for i, (name, goal) in enumerate(heads):
    prev = re.sub(r"<[^>]+>", " ", " ".join(parts))[-400:]
    if i == 0: extra = "این بخش مقدمه است؛ مسئله را زنده کن و خواننده را وارد بحث کن."
    elif i == len(heads) - 1: extra = "این بخش جمع‌بندی است؛ کوتاه جمع‌بندی کن و با یک سؤال برای خواننده تمام کن."
    else: extra = "اگر بخش بلند شد، یک یا دو زیرعنوان h3 بگذار."
    body = clean(ask(f"""مقاله: «{title}» | کلمه‌ی کلیدی: {kw}
فهرست بخش‌ها: {names}

حالا فقط بخش «{name}» را بنویس. هدف این بخش: {goal}. {extra}
حدود ۲۸۰ تا ۳۵۰ کلمه بنویس (کوتاه‌تر نباشد)، با توضیح کافی، مثال یا جزئیات.
۲ تا ۴ عبارت یا جمله‌ی کلیدی را با <strong> پررنگ کن، نه بیشتر.
فقط HTML ساده (p, ul, li, strong, h3). تیتر h2 نگذار و مطالب بخش‌های دیگر را تکرار نکن.
پایان متن قبلی (تکرارش نکن): {prev}""", 1800))
    parts.append(("" if i == 0 else f"<h2>{name}</h2>\n") + body + "\n")
html = "\n".join(parts)
words = len(re.sub(r"<[^>]+>", " ", html).split())
print("Word count:", words, "(کمتر از ۱۲۰۰ است!)" if words < 1200 else "")

# درخواست آخر: سئو و تصویر
s = ask(f"""برای مقاله‌ی «{title}» با کلمه‌ی کلیدی «{kw}» دقیقاً در این قالب بنویس، هر مورد در یک خط:
META_TITLE: حداکثر ۶۰ کاراکتر، بدون کلیشه
META_DESC: ۱۴۰ تا ۱۶۰ کاراکتر، جذاب و بدون عبارت کلیشه‌ای
EXCERPT: ۲ جمله
TAGS: ۴ تا ۵ برچسب جداشده با علامت |
ALT: متن جایگزین تصویر شاخص به فارسی، یک جمله‌ی توصیفی کوتاه شامل کلمه‌ی کلیدی
IMG_PROMPT: یک جمله‌ی انگلیسی که یک استعاره‌ی تصویری ساده برای موضوع مقاله را توصیف کند، بدون هیچ متن یا حرف
Q1: سؤال واقعی یک مدیر کسب‌وکار
A1: پاسخ ۲ تا ۳ جمله
Q2: ...
A2: ...
Q3: ...
A3: ...""", 1400)
meta_title = grab(s, "META_TITLE")[:60] or title[:60]
meta_desc = grab(s, "META_DESC")[:160]
excerpt = grab(s, "EXCERPT")
alt = grab(s, "ALT") or title
img_idea = grab(s, "IMG_PROMPT") or "a simple visual metaphor for growing a small business"
tags = [x.strip() for x in grab(s, "TAGS").split("|") if x.strip()] or [x.strip() for x in kw2.split("،") if x.strip()]
faq = [(grab(s, f"Q{i}"), grab(s, f"A{i}")) for i in (1, 2, 3)]
faq = [(q, a) for q, a in faq if q and a]
if faq:
    html += "\n<h2>سوالات متداول</h2>\n" + "".join(f"<h3>{q}</h3>\n<p>{a}</p>\n" for q, a in faq)

cats = requests.get(f"{WP}/wp-json/wp/v2/categories", params={"per_page": 100}, auth=AUTH, timeout=30).json()
cat_ids = [c["id"] for c in cats if c["name"].strip() == row["category"].strip()]
tag_ids = []
for tg in tags[:5]:
    tr = requests.post(f"{WP}/wp-json/wp/v2/tags", auth=AUTH, json={"name": tg}, timeout=30)
    if tr.status_code in (200, 201): tag_ids.append(tr.json()["id"])
    elif tr.status_code == 400 and "term_id" in tr.text: tag_ids.append(tr.json()["data"]["term_id"])

# تصویر شاخص (اختیاری)
media_id = None
if IMG_MODEL:
    img = make_image(f"Clean modern editorial illustration, flat vector style, soft calm colors, wide composition, no text, no letters, no logos. {img_idea}")
    if img:
        media_id = upload_image(img, slug, alt)
        print("Featured image ID:", media_id)
    else:
        print("Image generation failed; continuing without image.")

focus = ", ".join([kw] + [x.strip() for x in kw2.split("،") if x.strip()][:2])
payload = {"title": title, "slug": slug, "content": html, "excerpt": excerpt,
           "status": "draft", "categories": cat_ids, "tags": tag_ids,
           "meta": {"rank_math_title": meta_title, "rank_math_description": meta_desc,
                    "rank_math_focus_keyword": focus}}
if media_id: payload["featured_media"] = media_id
post = requests.post(f"{WP}/wp-json/wp/v2/posts", auth=AUTH, timeout=60, json=payload)
print("Create post:", post.status_code)
if post.status_code not in (200, 201): sys.exit(post.text[:300])
pid = post.json()["id"]
print("Draft ID:", pid, "| edit:", f"{WP}/wp-admin/post.php?post={pid}&action=edit")

chk = requests.get(f"{WP}/wp-json/wp/v2/posts/{pid}", params={"context": "edit"}, auth=AUTH, timeout=30).json()
m = chk.get("meta") or {}
print("Rank Math saved:", bool(m.get("rank_math_title")), "| focus:", m.get("rank_math_focus_keyword"))
print("META_TITLE:", meta_title); print("META_DESC:", meta_desc)

if "wp_id" not in fields: fields.append("wp_id")
row["status"] = "draft"; row["wp_id"] = str(pid)
with open("calendar.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
