import os, csv, re, sys, time, requests

WP = "https://mohammadmohajer.ir"
AUTH = (os.environ["WP_USER"], os.environ["WP_APP_PASSWORD"])
SYSTEM = open("prompt.md", encoding="utf-8").read()
GAP = os.environ.get("GAPGPT_API_KEY", "").strip()
OR_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"

def chat(url, key, model, user, max_tokens, extra=None):
    body = {"model": model, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": user}]}
    if extra: body.update(extra)
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

def grab(text, key):
    m = re.search(rf"^{key}\s*[:：]\s*(.+)$", text, re.M)
    return m.group(1).strip() if m else ""

r = requests.get(f"{WP}/wp-json/wp/v2/users/me", auth=AUTH, timeout=30)
print("WordPress:", r.status_code)
if r.status_code != 200: sys.exit("اتصال وردپرس درست نیست.")

with open("calendar.csv", encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f); fields = reader.fieldnames; rows = list(reader)
row = next((x for x in rows if x["status"].strip().lower() == "ready"), None)
if not row: sys.exit("ردیفی با وضعیت ready نیست.")
kw2 = row["secondary_keywords"].replace("|", "، ")
print("Topic:", row["topic"])

# درخواست ۱: مقاله
raw = ask(f"""موضوع: {row['topic']}
کلمه‌ی کلیدی اصلی: {row['primary_keyword']} (طبیعی و بدون تکرار اجباری در متن بیاور)
کلمات فرعی: {kw2}

خروجی را دقیقاً با این دو خط شروع کن و بعد مقاله‌ی HTML را بنویس:
TITLE: عنوان جذاب مقاله
SLUG: english-short-slug
""", 7000)
title = grab(raw, "TITLE") or row["topic"]
slug = re.sub(r"[^a-z0-9-]", "", grab(raw, "SLUG").lower().replace(" ", "-"))[:60].strip("-") or f"article-{row['id']}"
html = re.sub(r"^(TITLE|SLUG)\s*[:：].*$", "", raw, flags=re.M)
html = re.sub(r"```(html)?", "", html).strip()
html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
print("Title:", title, "| words:", len(re.sub(r"<[^>]+>", " ", html).split()))

dup = requests.get(f"{WP}/wp-json/wp/v2/posts", params={"slug": slug, "status": "any"}, auth=AUTH, timeout=30).json()
if isinstance(dup, list) and dup: sys.exit("مقاله‌ای با این slug قبلاً هست: " + slug)

# درخواست ۲: سئو
s = ask(f"""برای مقاله‌ی «{title}» با کلمه‌ی کلیدی «{row['primary_keyword']}» دقیقاً در این قالب بنویس، هر مورد در یک خط:
META_TITLE: حداکثر ۶۰ کاراکتر
META_DESC: ۱۴۰ تا ۱۶۰ کاراکتر
EXCERPT: ۲ جمله
TAGS: ۴ تا ۵ برچسب جداشده با علامت |
Q1: سؤال واقعی یک مدیر کسب‌وکار
A1: پاسخ ۲ تا ۳ جمله
Q2: ...
A2: ...
Q3: ...
A3: ...""", 1200)
meta_title = grab(s, "META_TITLE") or title
meta_desc, excerpt = grab(s, "META_DESC"), grab(s, "EXCERPT")
tags = [x.strip() for x in grab(s, "TAGS").split("|") if x.strip()] or [x.strip() for x in kw2.split("،") if x.strip()]
faq = [(grab(s, f"Q{i}"), grab(s, f"A{i}")) for i in (1, 2, 3)]
faq = [(q, a) for q, a in faq if q and a]
if faq and "سوالات متداول" not in html:
    html += "\n<h2>سوالات متداول</h2>\n" + "".join(f"<h3>{q}</h3>\n<p>{a}</p>\n" for q, a in faq)

cats = requests.get(f"{WP}/wp-json/wp/v2/categories", params={"per_page": 100}, auth=AUTH, timeout=30).json()
cat_ids = [c["id"] for c in cats if c["name"].strip() == row["category"].strip()]
tag_ids = []
for tg in tags[:5]:
    tr = requests.post(f"{WP}/wp-json/wp/v2/tags", auth=AUTH, json={"name": tg}, timeout=30)
    if tr.status_code in (200, 201): tag_ids.append(tr.json()["id"])
    elif tr.status_code == 400 and "term_id" in tr.text: tag_ids.append(tr.json()["data"]["term_id"])

post = requests.post(f"{WP}/wp-json/wp/v2/posts", auth=AUTH, timeout=60, json={
    "title": title, "slug": slug, "content": html, "excerpt": excerpt,
    "status": "draft", "categories": cat_ids, "tags": tag_ids})
print("Create post:", post.status_code)
if post.status_code not in (200, 201): sys.exit(post.text[:300])
pid = post.json()["id"]
print("Draft ID:", pid, "| edit:", f"{WP}/wp-admin/post.php?post={pid}&action=edit")
print("META_TITLE:", meta_title); print("META_DESC:", meta_desc)

if "wp_id" not in fields: fields.append("wp_id")
row["status"] = "draft"; row["wp_id"] = str(pid)
with open("calendar.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
