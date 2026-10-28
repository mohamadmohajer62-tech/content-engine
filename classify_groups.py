"""
دسته‌بندی خودکار مقاله‌های نشریه در ۸ گروه (taxonomy «گروه‌های نشریه»).
هر اجرا تا ۴۰ مقاله‌ی بدون گروه (پیش‌نویس هم) را با مدل زبانی گروه‌بندی می‌کند؛
اگر مدل پاسخ ندهد، قاعده‌ی کلیدواژه‌ای جایگزین می‌شود.
"""
import os, re, sys
import generate as g
import brand_render as b

API = g.WP + "/wp-json/mm-magazine/v1"
GROUPS = {
    "diagnosis": ("تشخیص و تحلیل بازار", "کشف مسئله، تحلیل بازار و رقبا، SWOT، شناخت وضعیت فعلی"),
    "positioning": ("جایگاه‌یابی و برندینگ", "بازار هدف، پرسونا، ارزش پیشنهادی، مزیت رقابتی، برندینگ"),
    "pricing": ("قیمت‌گذاری و پیشنهاد فروش", "قیمت‌گذاری، پیشنهاد فروش، هدف‌گذاری و KPI"),
    "acquisition": ("جذب مشتری و بازاریابی", "بازاریابی محتوا، دیجیتال مارکتینگ، تبلیغات، تولید لید، سئو"),
    "sales": ("فروش و تبدیل", "فرآیند فروش، مذاکره، تبدیل علاقه‌مند به مشتری"),
    "retention": ("نگهداشت و وفاداری", "حفظ مشتری، فروش مجدد به مشتریان فعلی، تجربه‌ی مشتری، ارجاع"),
    "systems": ("سیستم‌سازی و مدیریت رشد", "آزمایش‌گری، داشبورد، اتوماسیون، فرآیندها، مدیریت تیم و ظرفیت اجرایی"),
    "tools": ("ابزار، الگو و تجربه‌ها", "قالب‌ها، چک‌لیست‌ها، پادکست، وبینار، کتاب، تجربه‌ی کسب‌وکارها"),
}
RULES = [  # ترتیب مهم است
    ("tools", ["قالب", "چک‌لیست", "چک لیست", "تمپلیت", "پادکست", "وبینار", "کتاب", "ابزار", "دانلود"]),
    ("retention", ["نگهداشت", "وفاداری", "مشتریان فعلی", "مشتری فعلی", "فروش مجدد", "ارجاع", "تجربه مشتری", "تجربه‌ی مشتری"]),
    ("pricing", ["قیمت", "پیشنهاد فروش", "kpi", "هدف‌گذاری", "تخفیف"]),
    ("positioning", ["برند", "جایگاه", "ارزش پیشنهادی", "مزیت رقابتی", "پرسونا", "بازار هدف"]),
    ("diagnosis", ["swot", "تحلیل", "رقبا", "تشخیص", "وضعیت", "کشف مسئله"]),
    ("systems", ["سیستم", "اتوماسیون", "داشبورد", "آزمایش", "مدیریت رشد", "فرآیند", "تیم"]),
    ("acquisition", ["جذب", "بازاریابی", "محتوا", "تبلیغ", "سئو", "شبکه‌های اجتماعی", "لید"]),
    ("sales", ["فروش", "تبدیل", "مذاکره", "قیف"]),
]


def rule_group(text):
    t = text.lower()
    for slug, words in RULES:
        if any(w in t for w in words):
            return slug
    return "acquisition"


def llm_group(title, excerpt, cats):
    lines = "\n".join("%s: %s — %s" % (s, n, d) for s, (n, d) in GROUPS.items())
    j = b.ask_json(g, (
        "گروه‌های نشریه:\n%s\n\nمقاله:\nعنوان: %s\nچکیده: %s\nدسته‌های قدیمی سایت: %s\n\n"
        "نزدیک‌ترین گروه را انتخاب کن. (مثلاً «فروش مجدد به مشتریان فعلی» یعنی retention.)\n"
        'خروجی: {"group": "یکی از کلیدهای بالا"}' % (lines, title, excerpt[:400], "، ".join(cats) or "—")), 120)
    slug = (j or {}).get("group", "")
    return slug if slug in GROUPS else ""


r = g.wp("GET", API + "/ungrouped", tries=3, auth=g.AUTH, timeout=90)
if r.status_code != 200:
    sys.exit("فهرست مقاله‌های بدون گروه در دسترس نیست (HTTP %s). افزونه‌ی نشریه به‌روز است؟" % r.status_code)
posts = r.json().get("posts", [])
if not posts:
    print("همه‌ی مقاله‌ها گروه دارند.")
    sys.exit(0)

t = g.wp("GET", g.WP + "/wp-json/wp/v2/mm_group?per_page=50", tries=3, auth=g.AUTH, timeout=90)
if t.status_code != 200:
    sys.exit("گروه‌های نشریه در وردپرس پیدا نشد (HTTP %s). یک بار به سایت سر بزنید تا ساخته شوند." % t.status_code)
term_id = {x["slug"]: x["id"] for x in t.json()}
print("Terms:", term_id)

done, rows = 0, []
for p in posts:
    slug = llm_group(p["title"], p["excerpt"], p["cats"]) or rule_group(p["title"] + " " + p["excerpt"] + " " + " ".join(p["cats"]))
    tid = term_id.get(slug)
    if not tid:
        print("No term for", slug, "- skipped", p["id"])
        continue
    try:
        u = g.wp("POST", "%s/wp-json/wp/v2/posts/%s" % (g.WP, p["id"]), tries=3, auth=g.AUTH, timeout=90, json={"mm_group": [tid]})
    except Exception as e:
        print("Failed", p["id"], type(e).__name__)
        continue
    print("%s -> %s (HTTP %s) | %s" % (p["id"], slug, u.status_code, p["title"][:60]))
    if u.status_code == 200:
        done += 1
        rows.append("• %s ← %s" % (GROUPS[slug][0], p["title"][:50]))

print("Classified %d of %d." % (done, len(posts)))
if done:
    g.notify("🗂 %d مقاله در گروه‌های نشریه دسته‌بندی شد:\n%s" % (done, "\n".join(rows[:12])))
