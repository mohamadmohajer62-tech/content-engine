import os, csv, re, sys, glob, requests

WP = "https://mohammadmohajer.ir"
AUTH = (os.environ["WP_USER"], os.environ["WP_APP_PASSWORD"])
KEY = os.environ["OPENROUTER_API_KEY"]
SYSTEM = open("prompt.md", encoding="utf-8").read()
ALLOWED = {"SWOT", "TOWS", "KPI"}

# True یعنی فقط مدل‌هایی که روی پرامپت آموزش نمی‌بینند. اگر هیچ مدلی جواب نداد، موقتاً False کنید.
DENY_TRAINING = True

def free_models():
    try:
        data = requests.get("https://openrouter.ai/api/v1/models", timeout=30).json()["data"]
    except Exception as e:
        sys.exit("لیست مدل‌ها دریافت نشد: " + str(e))
    out = []
    for m in data:
        p = m.get("pricing", {})
        try:
            free = float(p.get("prompt", "1")) == 0 and float(p.get("completion", "1")) == 0
        except Exception:
            free = False
        mid = m["id"]
        if not free or "stealth" in mid or mid.startswith("openrouter/"):
            continue
        if (m.get("context_length") or 0) < 16000:
            continue
        out.append(m)
    out.sort(key=lambda m: m.get("created", 0), reverse=True)
    return [m["id"] for m in out]

MODELS = free_models()
print("Free models found:", len(MODELS), MODELS[:8])
if not MODELS:
    sys.exit("هیچ مدل رایگانی پیدا نشد.")
good = [0]

def ask(user, max_tokens=3000):
    order = MODELS[good[0]:] + MODELS[:good[0]]
    for model in order[:10]:
        body = {"model": model, "max_tokens": max_tokens,
                "messages": [{"role": "system", "content": SYSTEM},
                             {"role": "user", "content": user}]}
        if DENY_TRAINING:
            body["provider"] = {"data_collection": "deny"}
        try:
            r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                              headers={"Authorization": f"Bearer {KEY}"},
                              json=body, timeout=240)
            if r.status_code != 200:
                print(f"[{model}] status {r.status_code} {r.text[:150]}")
                continue
            text = r.json()["choices"][0]["message"].get("content") or ""
            if len(text) > 50:
                good[0] = MODELS.index(model)
                print(f"[{model}] OK")
                return text
            print(f"[{model}] empty answer")
        except Exception as e:
            print(f"[{model}] error {type(e).__name__}")
    sys.exit("هیچ مدل رایگانی پاسخ نداد. اگر DENY_TRAINING روشن است، آن را موقتاً False کنید یا بعداً تلاش کنید.")

def clean(t):
    t = re.sub(r"```(html)?", "", t).strip()
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)

def grab(text, key):
    m = re.search(rf"^{key}\s*[:：]\s*(.+)$", text, re.M)
    return m.group(1).strip() if m else ""

def latin_words(html):
    text = re.sub(r"<[^>]+>", " ", html)
    return sorted({w for w in re.findall(r"[A-Za-z]{3,}", text) if w.upper() not in ALLOWED})

def load_cards(ids):
    parts = []
    for cid in ids:
        for p in glob.glob(f"sources/cards/{cid}-*.md") + glob.glob(f"sources/cards/{cid}.md"):
            parts.append(open(p, encoding="utf-8").read())
    if not parts:
        sys.exit("کارت منبع پیدا نشد: " + ", ".join(ids))
    return "\n\n=====\n\n".join(parts)

ROLES = [
    ("مقدمه", "با یک موقعیت تصمیم‌گیری واقعی‌نما شروع کن، نه تعریف انتزاعی. سؤال محوری کارت را مطرح کن."),
    ("تعریف دقیق", "مفهوم را دقیقاً طبق کارت تعریف کن و مرزش را با اشتباهات مشابه روشن کن."),
    ("سازوکار و هزینه‌ی اشتباه", "توضیح بده چرا این اشتباه رخ می‌دهد و چرا گران است، با زنجیره‌ی علامت، برداشت، تصمیم، پیامد؛ فقط از ایده‌ی مرکزی کارت."),
    ("نمونه‌های فرضی", "دو نمونه‌ی کارت را با عبارت «فرض کنید» بنویس: تصمیم، اشتباه و پیامد."),
    ("نشانه‌های تشخیص", "نشانه‌هایی که مدیر می‌تواند در کسب‌وکار خودش ببیند، از بخش «جایی که خراب می‌شود» کارت."),
    ("روش اصلاح گام‌به‌گام", "مسیر عملی کارت را با توضیح اجرایی هر گام بنویس، بدون گام تازه."),
    ("جایگاه در مدل ۱۷ مرحله‌ای", "مرحله و بلوک این موضوع و پیوندش با مرحله‌ی قبل و بعد را طبق کارت بگو، بدون ساخت جزئیات."),
    ("ابزار اجرایی و گام بعدی", "چک‌لیست کارت را بیاور و با دعوت به اقدام پایانی تمام کن."),
]

# 1) چک وردپرس
r = requests.get(f"{WP}/wp-json/wp/v2/users/me", auth=AUTH, timeout=30)
print("WordPress:", r.status_code)
if r.status_code != 200:
    sys.exit("اتصال وردپرس درست نیست.")

# 2) ردیف ready
with open("calendar.csv", encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    fields = reader.fieldnames
    rows = list(reader)
row = next((x for x in rows if x["status"].strip().lower() == "ready"), None)
if not row:
    sys.exit("ردیفی با وضعیت ready نیست.")
kw2 = row["secondary_keywords"].replace("|", "، ")
card_ids = [c.strip() for c in row.get("cards", "").split("|") if c.strip()]
CARDS = load_cards(card_ids)
print("Topic:", row["topic"], "| cards:", card_ids)

# 3) طرح کلی (قالب خطی، نه JSON)
roles_text = "\n".join(f"{i+1}. {n}" for i, (n, _) in enumerate(ROLES))
t = ask(f"""موضوع: {row['topic']}
کلمه‌ی کلیدی اصلی: {row['primary_keyword']}
کلمات فرعی: {kw2}

کارت منبع:
{CARDS}

مقاله ۸ بخش دارد با این وظایف:
{roles_text}

یک عنوان جذاب شامل کلمه‌ی کلیدی، یک slug انگلیسی کوتاه، و ۸ زیرعنوان خوانا بده (زیرعنوان اول فقط «مقدمه» است).
دقیقاً در همین قالب و بدون هیچ توضیح دیگر:
TITLE: ...
SLUG: ...
H1: مقدمه
H2: ...
H3: ...
H4: ...
H5: ...
H6: ...
H7: ...
H8: ...""", 800)
title = grab(t, "TITLE") or row["topic"]
slug = re.sub(r"[^a-z0-9-]", "", grab(t, "SLUG").lower().replace(" ", "-"))[:60].strip("-") or f"article-{row['id']}"
headings = re.findall(r"^H\d\s*[:：]\s*(.+)$", t, re.M)
if len(headings) != 8:
    print("Outline headings not parsed, using defaults.")
    headings = [n for n, _ in ROLES]
print("Title:", title, "| slug:", slug)

# 4) تکراری نبودن
dup = requests.get(f"{WP}/wp-json/wp/v2/posts", params={"slug": slug, "status": "any"}, auth=AUTH, timeout=30).json()
if isinstance(dup, list) and dup:
    sys.exit("مقاله‌ای با این slug قبلاً هست: " + slug)

# 5) نوشتن بخش‌ها
sections = []
for i, (role, how) in enumerate(ROLES):
    tail = re.sub(r"<[^>]+>", " ", " ".join(sections))[-500:]
    cta_line = ("در پایان این دعوت به اقدام را بیاور: " + row["cta"]) if i == 7 else ""
    body = clean(ask(f"""مقاله: «{title}» | کلمه‌ی کلیدی: {row['primary_keyword']}
فهرست بخش‌ها: {' | '.join(headings)}

کارت منبع (تنها مرجع مجاز برای تعریف‌ها و مراحل):
{CARDS}

حالا فقط بخش «{headings[i]}» را بنویس.
وظیفه‌ی این بخش: {how}
حدود ۲۵۰ تا ۳۵۰ کلمه، فقط HTML ساده (p, ul, li, strong). تیتر H2 نگذار.
پایان متن قبلی (تکرارش نکن): {tail}
{cta_line}""", 1800))
    sections.append(("" if i == 0 else f"<h2>{headings[i]}</h2>\n") + body + "\n")

# 6) ویرایش فارسی در دو بخش
def edit(block):
    out = clean(ask(f"""متن HTML زیر را ویرایش فارسی کن: جمله‌های ترجمه‌ای و غیرطبیعی را روان و طبیعی کن، کلمه‌های انگلیسی را فارسی کن (SWOT و TOWS و KPI بماند)، تکرار را کم کن.
معنا را تغییر نده، ادعا یا عدد تازه اضافه نکن، ساختار HTML و تیترهای h2 را حفظ کن. فقط HTML را برگردان.

{block}""", 3500))
    return out if len(out) > 0.6 * len(block) else block

edited = []
for h in ["".join(sections[:4]), "".join(sections[4:])]:
    e = edit(h)
    if latin_words(e):
        print("کلمه‌ی انگلیسی باقی‌مانده، ویرایش مجدد:", latin_words(e))
        e = edit(e)
    edited.append(e)
html = "\n".join(edited)
left = latin_words(html)
print("WARNING - English words left:" if left else "No stray English words.", left)

# 7) سئو و سوالات متداول (قالب خطی)
s = ask(f"""برای مقاله‌ی «{title}» با کلمه‌ی کلیدی «{row['primary_keyword']}» دقیقاً در این قالب بنویس، هر مورد فقط در یک خط و بدون توضیح دیگر:
META_TITLE: حداکثر ۶۰ کاراکتر
META_DESC: ۱۴۰ تا ۱۶۰ کاراکتر
EXCERPT: ۲ جمله
TAGS: ۴ تا ۵ برچسب جداشده با علامت |
Q1: سؤال واقعی یک مدیر کسب‌وکار
A1: پاسخ کاربردی ۲ تا ۳ جمله، فقط بر اساس کارت
Q2: ...
A2: ...
Q3: ...
A3: ...

کارت منبع:
{CARDS}""", 1200)
meta_title = grab(s, "META_TITLE") or title
meta_desc = grab(s, "META_DESC")
excerpt = grab(s, "EXCERPT")
tags = [x.strip() for x in grab(s, "TAGS").split("|") if x.strip()]
faq = [(grab(s, f"Q{i}"), grab(s, f"A{i}")) for i in (1, 2, 3)]
faq = [(q, a) for q, a in faq if q and a]
if faq:
    html += "\n<h2>سوالات متداول</h2>\n" + "".join(f"<h3>{q}</h3>\n<p>{a}</p>\n" for q, a in faq)

print("Word count:", len(re.sub(r"<[^>]+>", " ", html).split()))

# 8) دسته و برچسب
cats = requests.get(f"{WP}/wp-json/wp/v2/categories", params={"per_page": 100}, auth=AUTH, timeout=30).json()
cat_ids = [c["id"] for c in cats if c["name"].strip() == row["category"].strip()]
tag_ids = []
for tg in tags[:5]:
    tr = requests.post(f"{WP}/wp-json/wp/v2/tags", auth=AUTH, json={"name": tg}, timeout=30)
    if tr.status_code in (200, 201):
        tag_ids.append(tr.json()["id"])
    elif tr.status_code == 400 and "term_id" in tr.text:
        tag_ids.append(tr.json()["data"]["term_id"])

# 9) پیش‌نویس
post = requests.post(f"{WP}/wp-json/wp/v2/posts", auth=AUTH, timeout=60, json={
    "title": title, "slug": slug, "content": html, "excerpt": excerpt,
    "status": "draft", "categories": cat_ids, "tags": tag_ids})
print("Create post:", post.status_code)
if post.status_code not in (200, 201):
    sys.exit(post.text[:300])
pid = post.json()["id"]
print("Draft ID:", pid, "| edit:", f"{WP}/wp-admin/post.php?post={pid}&action=edit")
print("META_TITLE:", meta_title)
print("META_DESC:", meta_desc)

# 10) به‌روزرسانی تقویم
if "wp_id" not in fields: fields.append("wp_id")
row["status"] = "draft"; row["wp_id"] = str(pid)
with open("calendar.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
