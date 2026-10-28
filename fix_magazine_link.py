"""
اصلاح یک‌باره‌ی لینک نشریه در مقاله‌های قبلی:
  https://mohammadmohajer.ir/category/business-growth-magazine/  ->  https://mohammadmohajer.ir/business-growth-magazine/
APPLY=0 (پیش‌فرض): فقط می‌شمارد  |  APPLY=1: اعمال می‌کند
"""
import os, re, sys
import generate as g

APPLY = os.environ.get("APPLY", "0").strip() in ("1", "true", "yes")
OLD = re.compile(r"https://mohammadmohajer\.ir/category/business-growth-magazine/?(?=[\"'\s<>])")
NEW = "https://mohammadmohajer.ir/business-growth-magazine/"

page, found, changed = 1, 0, 0
while True:
    r = g.wp("GET", "%s/wp-json/wp/v2/posts" % g.WP, tries=3, auth=g.AUTH, timeout=120,
             params={"per_page": 20, "page": page, "context": "edit", "status": "publish,draft,pending,future,private",
                     "_fields": "id,content,title"})
    if r.status_code == 400:      # بعد از آخرین صفحه
        break
    if r.status_code != 200:
        sys.exit("دریافت مقاله‌ها ناموفق (HTTP %s)" % r.status_code)
    posts = r.json()
    if not posts:
        break
    for p in posts:
        raw = (p.get("content") or {}).get("raw", "") or ""
        n = len(OLD.findall(raw))
        if not n:
            continue
        found += 1
        title = (p.get("title") or {}).get("raw", "")[:50]
        print("%s | %d لینک | %s" % (p["id"], n, title))
        if APPLY:
            new = OLD.sub(NEW, raw)
            u = g.wp("POST", "%s/wp-json/wp/v2/posts/%s" % (g.WP, p["id"]), tries=3, auth=g.AUTH, timeout=180, json={"content": new})
            print("   ->", "OK" if u.status_code == 200 else "HTTP %s" % u.status_code)
            changed += 1 if u.status_code == 200 else 0
    page += 1

print("\nمقاله‌های دارای لینک قدیمی: %d | اصلاح‌شده: %d | حالت: %s" % (found, changed, "اعمال" if APPLY else "فقط شمارش (APPLY=1 را بزنید)"))
