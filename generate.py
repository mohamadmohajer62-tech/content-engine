import os, csv, json, re, sys, glob, requests

WP = "https://mohammadmohajer.ir"
AUTH = (os.environ["WP_USER"], os.environ["WP_APP_PASSWORD"])
KEY = os.environ["OPENROUTER_API_KEY"]
SYSTEM = open("prompt.md", encoding="utf-8").read()
ALLOWED = {"SWOT", "TOWS", "KPI"}

PREFERRED = [
    "deepseek/deepseek-chat-v3-0324:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen-2.5-72b-instruct:free",
]

def discover_free():
    try:
        data = requests.get("https://openrouter.ai/api/v1/models", timeout=30).json()["data"]
        return [m["id"] for m in data if m["id"].endswith(":free")]
    except Exception:
        return []

MODELS = PREFERRED + [m for m in discover_free() if m not in PREFERRED]

def ask(user, max_tokens=3000):
    for model in MODELS[:8]:
        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {KEY}"},
                json={"model": model, "max_tokens": max_tokens,
                      "messages": [{"role": "system", "content": SYSTEM},
                                   {"role": "user", "content": user}]},
                timeout=240)
            if r.status_code != 200:
                print(f"[{model}] status {r.status_code}"); continue
            text = r.json()["choices"][0]["message"]["content"]
            if text and len(text) > 50:
                print(f"[{model}] OK"); return text
        except Exception as e:
            print(f"[{model}] error {type(e).__name__}")
    sys.exit("هیچ مدل رایگانی پاسخ نداد؛ بعداً دوباره اجرا کنید.")

def ask_json(user):
    t = ask(user)
    m = re.search(r"\{.*\}", t, re.S)
    try:
        return json.loads(m.group(0))
    except Exception:
        sys.exit("خروجی JSON معتبر نبود: " + t[:300])

def clean(t):
    return re.sub(r"```(html)?", "", t).strip()

def latin_words(html):
    text = re.sub(r"<[^>]+>", " ", html)
    return sorted({w for w in re.findall(r"[A-Za-z]{3,}", text) if w.upper() not in ALLOWED})

def load_cards(ids):
    parts = []
    for cid in ids:
        files = glob.glob(f"sources/cards/{cid}-*.md") + glob.glob(f"sources/cards/{cid}.md")
        for p in files:
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

# 3) طرح کلی
roles_text = "\n".join(f"{i+1}. {n}" for i, (n, _) in enumerate(ROLES))
outline = ask_json(f"""موضوع: {row['topic']}
کلمه‌ی کلیدی اصلی: {row['primary_keyword']}
کلمات فرعی: {kw2}

کارت منبع:
{CARDS}

برای مقاله ۸ بخش با این وظایف داریم:
{roles_text}
یک عنوان جذاب شامل کلمه‌ی کلیدی و ۸ زیرعنوان خوانا و متناسب با موضوع بده (زیرعنوان اول فقط «مقدمه» است). فقط JSON:
{{"title": "...", "slug": "english-slug-with-dashes", "headings": ["مقدمه", "...", "..."]}}""")
title = outline["title"]
slug = re.sub(r"[^a-z0-9-]", "", outline["slug"].lower().replace(" ", "-")) or "article"
headings = outline["headings"] if len(outline.get("headings", [])) == 8 else [n for n, _ in ROLES]

# 4) تکراری نبودن
dup = requests.get(f"{WP}/wp-json/wp/v2/posts", params={"slug": slug, "status": "any"}, auth=AUTH, timeout=30).json()
if isinstance(dup, list) and dup:
    sys.exit("مقاله‌ای با این slug قبلاً هست: " + slug)

# 5) نوشتن بخش‌ها
sections = []
for i, (role, how) in enumerate(ROLES):
    tail = re.sub(r"<[^>]+>", " ", " ".join(sections))[-500:]
    body = clean(ask(f"""مقاله: «{title}» | کلمه‌ی کلیدی: {row['primary_keyword']}
فهرست بخش‌ها: {' | '.join(headings)}

کارت منبع (تنها مرجع مجاز برای تعریف‌ها و مراحل):
{CARDS}

حالا فقط بخش «{headings[i]}» را بنویس.
وظیفه‌ی این بخش: {how}
حدود ۲۵۰ تا ۳۵۰ کلمه، فقط HTML ساده (p, ul, li, strong). تیتر H2 نگذار.
پایان متن قبلی (تکرارش نکن): {tail}
{'در پایان این دعوت به اقدام را بیاور: ' + row['cta'] if i == 7 else ''}""", 1800))
    sections.append(("" if i == 0 else f"<h2>{headings[i]}</h2>\n") + body + "\n")

# 6) ویرایش فارسی در دو بخش
def edit(block):
    out = clean(ask(f"""متن HTML زیر را ویرایش فارسی کن: جمله‌های ترجمه‌ای و غیرطبیعی را روان و طبیعی کن، کلمه‌های انگلیسی را فارسی کن (SWOT و TOWS و KPI بماند)، تکرار را کم کن.
معنا را تغییر نده، ادعا یا عدد تازه اضافه نکن، ساختار HTML و تیترهای h2 را حفظ کن. فقط HTML را برگردان.

{block}""", 3500))
    return out if len(out) > 0.6 * len(block) else block

halves = ["".join(sections[:4]), "".join(sections[4:])]
edited = []
for h in halves:
    e = edit(h)
    if latin_words(e):
        print("کلمه‌ی انگلیسی باقی‌مانده، ویرایش مجدد:", latin_words(e))
        e = edit(e)
    edited.append(e)
html = "\n".join(edited)
left = latin_words(html)
print("WARNING - English words left:" if left else "No stray English words.", left)

# 7) سئو و سوالات متداول
seo = ask_json(f"""برای مقاله‌ی «{title}» با کلمه‌ی کلیدی «{row['primary_keyword']}» فقط JSON بده:
{{"meta_title": "حداکثر ۶۰ کاراکتر", "meta_description": "۱۴۰ تا ۱۶۰ کاراکتر",
 "excerpt": "۲ جمله", "tags": ["۴ تا ۵ برچسب"],
 "faq": [{{"q": "سؤال واقعی یک مدیر کسب‌وکار", "a": "پاسخ کاربردی ۲ تا ۳ جمله، فقط بر اساس کارت"}},
         {{"q": "...", "a": "..."}}, {{"q": "...", "a": "..."}}]}}
کارت منبع:
{CARDS}""")
html += "\n<h2>سوالات متداول</h2>\n" + "".join(
    f"<h3>{x['q']}</h3>\n<p>{x['a']}</p>\n" for x in seo["faq"])

words = len(re.sub(r"<[^>]+>", " ", html).split())
print("Word count:", words)

# 8) دسته و برچسب
cats = requests.get(f"{WP}/wp-json/wp/v2/categories", params={"per_page": 100}, auth=AUTH, timeout=30).json()
cat_ids = [c["id"] for c in cats if c["name"].strip() == row["category"].strip()]
tag_ids = []
for t in seo["tags"][:5]:
    tr = requests.post(f"{WP}/wp-json/wp/v2/tags", auth=AUTH, json={"name": t}, timeout=30)
    if tr.status_code in (200, 201):
        tag_ids.append(tr.json()["id"])
    elif tr.status_code == 400 and "term_id" in tr.text:
        tag_ids.append(tr.json()["data"]["term_id"])

# 9) پیش‌نویس
post = requests.post(f"{WP}/wp-json/wp/v2/posts", auth=AUTH, timeout=60, json={
    "title": title, "slug": slug, "content": html, "excerpt": seo["excerpt"],
    "status": "draft", "categories": cat_ids, "tags": tag_ids})
print("Create post:", post.status_code)
if post.status_code not in (200, 201):
    sys.exit(post.text[:300])
pid = post.json()["id"]
print("Draft ID:", pid, "| edit:", f"{WP}/wp-admin/post.php?post={pid}&action=edit")
print("META_TITLE:", seo["meta_title"])
print("META_DESC:", seo["meta_description"])

# 10) به‌روزرسانی تقویم
if "wp_id" not in fields: fields.append("wp_id")
row["status"] = "draft"; row["wp_id"] = str(pid)
with open("calendar.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
