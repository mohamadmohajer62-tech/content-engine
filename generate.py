import os, csv, json, re, sys, requests

WP = "https://mohammadmohajer.ir"
AUTH = (os.environ["WP_USER"], os.environ["WP_APP_PASSWORD"])
KEY = os.environ["OPENROUTER_API_KEY"]
SYSTEM = open("prompt.md", encoding="utf-8").read()

# نام مدل‌های رایگان ممکن است تغییر کند؛ اگر هیچ‌کدام کار نکرد، خودکار از لیست OpenRouter پیدا می‌شود
PREFERRED = [
    "deepseek/deepseek-chat-v3-0324:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen-2.5-72b-instruct:free",
]

def discover_free():
    try:
        data = requests.get("https://openrouter.ai/api/v1/models", timeout=30).json()["data"]
        ids = [m["id"] for m in data if m["id"].endswith(":free")]
        return ids
    except Exception:
        return []

MODELS = PREFERRED + [m for m in discover_free() if m not in PREFERRED]

def ask(user, max_tokens=3500):
    for model in MODELS[:12]:
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

# 1) چک وردپرس
r = requests.get(f"{WP}/wp-json/wp/v2/users/me", auth=AUTH, timeout=30)
print("WordPress:", r.status_code, r.text[:200])
if r.status_code != 200:
    sys.exit("اتصال وردپرس درست نیست (۴۰۱ یعنی نام کاربری یا Application Password اشتباه است).")

# 2) خواندن اولین ردیف ready
with open("calendar.csv", encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    fields = reader.fieldnames
    rows = list(reader)
row = next((x for x in rows if x["status"].strip().lower() == "ready"), None)
if not row:
    sys.exit("ردیفی با وضعیت ready نیست.")
kw2 = row["secondary_keywords"].replace("|", "، ")
print("Topic:", row["topic"])

# 3) طرح کلی
outline = ask_json(f"""موضوع: {row['topic']}
کلمه‌ی کلیدی اصلی: {row['primary_keyword']}
کلمات فرعی: {kw2}
یک طرح کلی برای مقاله‌ای حدود ۲۰۰۰ کلمه بده. فقط JSON:
{{"title": "عنوان جذاب شامل کلمه‌ی کلیدی", "slug": "english-slug-with-dashes",
 "sections": ["مقدمه", "زیرعنوان ۲", "...", "جمع‌بندی و گام بعدی"]}}
بین ۶ تا ۸ بخش، اولی «مقدمه» و آخری «جمع‌بندی و گام بعدی».""")
title = outline["title"]
slug = re.sub(r"[^a-z0-9-]", "", outline["slug"].lower().replace(" ", "-")) or "article"

# 4) جلوگیری از تکرار
dup = requests.get(f"{WP}/wp-json/wp/v2/posts", params={"slug": slug, "status": "any"}, auth=AUTH, timeout=30).json()
if isinstance(dup, list) and dup:
    sys.exit("مقاله‌ای با این slug قبلاً هست: " + slug)

# 5) نوشتن بخش‌ها
html = ""
for i, sec in enumerate(outline["sections"]):
    tail = re.sub(r"<[^>]+>", " ", html)[-600:]
    body = ask(f"""مقاله: «{title}» | کلمه‌ی کلیدی: {row['primary_keyword']}
فهرست بخش‌ها: {' | '.join(outline['sections'])}
حالا فقط بخش «{sec}» را بنویس، حدود ۳۰۰ تا ۴۰۰ کلمه.
خروجی فقط HTML ساده (p, ul, li, strong). {'' if i == 0 else 'تیتر H2 را خودت نگذار؛ من می‌گذارم.'}
انتهای متن قبلی (برای پیوستگی، تکرارش نکن): {tail}
{'در بخش آخر، با CTA زیر تمام کن: ' + row['cta'] if i == len(outline['sections']) - 1 else ''}""", 1800)
    body = re.sub(r"```(html)?", "", body).strip()
    html += (f"<h2>{sec}</h2>\n" if i > 0 else "") + body + "\n"

# 6) سئو و سوالات متداول
seo = ask_json(f"""برای مقاله‌ی «{title}» با کلمه‌ی کلیدی «{row['primary_keyword']}» فقط JSON بده:
{{"meta_title": "حداکثر ۶۰ کاراکتر", "meta_description": "حدود ۱۴۰ تا ۱۶۰ کاراکتر",
 "excerpt": "۲ جمله", "tags": ["۴ تا ۵ برچسب"],
 "faq": [{{"q": "...", "a": "..."}}, {{"q": "...", "a": "..."}}, {{"q": "...", "a": "..."}}]}}""")
html += "<h2>سوالات متداول</h2>\n" + "".join(
    f"<h3>{x['q']}</h3>\n<p>{x['a']}</p>\n" for x in seo["faq"])

# 7) دسته و برچسب‌ها
cats = requests.get(f"{WP}/wp-json/wp/v2/categories", params={"per_page": 100}, auth=AUTH, timeout=30).json()
cat_ids = [c["id"] for c in cats if c["name"].strip() == row["category"].strip()]
tag_ids = []
for t in seo["tags"][:5]:
    tr = requests.post(f"{WP}/wp-json/wp/v2/tags", auth=AUTH, json={"name": t}, timeout=30)
    if tr.status_code in (200, 201):
        tag_ids.append(tr.json()["id"])
    elif tr.status_code == 400 and "term_id" in tr.text:
        tag_ids.append(tr.json()["data"]["term_id"])

# 8) ساخت پیش‌نویس
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

# 9) به‌روزرسانی تقویم
if "wp_id" not in fields: fields.append("wp_id")
row["status"] = "draft"; row["wp_id"] = str(pid)
with open("calendar.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
