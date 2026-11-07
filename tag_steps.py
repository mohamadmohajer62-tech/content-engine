# -*- coding: utf-8 -*-
"""برچسب‌گذاری مقاله‌ها بر اساس گام‌های مدل ۱۷ مرحله‌ای (step-1 تا step-17).
MODE=calendar : مقاله‌های تقویم (ستون wp_id) را از روی steps.csv برچسب می‌زند (رایگان، بدون هوش مصنوعی).
MODE=ai       : مقاله‌های منتشرشده‌ی دیگری که هنوز برچسب گام ندارند را با هوش مصنوعی دسته‌بندی می‌کند.
DRY_RUN=1 (پیش‌فرض) فقط گزارش می‌دهد و چیزی در وردپرس تغییر نمی‌دهد."""
import os, re, csv, sys
import generate as g

MODE = os.environ.get("MODE", "calendar").strip().lower()
DRY = os.environ.get("DRY_RUN", "1").strip() != "0"
LIMIT = int(os.environ.get("LIMIT", "40") or 40)

STEPS = {1: "کشف مسئله", 2: "فرضیه‌ی اولیه‌ی بازار هدف", 3: "تحلیل بازار و وضعیت فعلی", 4: "SWOT و TOWS",
         5: "بازار هدف نهایی", 6: "پرسونا و محرک خرید", 7: "ارزش پیشنهادی", 8: "مزیت رقابتی",
         9: "پیشنهاد فروش و قیمت‌گذاری", 10: "هدف‌گذاری کمّی و KPI", 11: "جذب مشتری", 12: "تبدیل و فروش",
         13: "نگهداشت و ارجاع", 14: "حلقه‌ی آزمایش‌گری", 15: "سیستم مدیریت رشد", 16: "حلقه‌ی بازگشتی به تشخیص",
         17: "ظرفیت اجرایی و منابع"}

_tag_cache = {}


def tag_id(n):
    if n in _tag_cache:
        return _tag_cache[n]
    if DRY:
        try:
            r = g.wp("GET", g.WP + "/wp-json/wp/v2/tags", tries=2, auth=g.AUTH, params={"slug": "step-%d" % n, "_fields": "id"}, timeout=60)
            _tag_cache[n] = r.json()[0]["id"] if r.status_code == 200 and r.json() else None
        except Exception:
            _tag_cache[n] = None
    else:
        _tag_cache[n] = g.ensure_step_tag(n)
    return _tag_cache[n]


def step_tag_set():
    """شناسه‌ی همه‌ی برچسب‌های step-N موجود (برای تشخیص پست‌های برچسب‌خورده)."""
    ids = {}
    try:
        r = g.wp("GET", g.WP + "/wp-json/wp/v2/tags", tries=3, auth=g.AUTH, params={"search": "step-", "per_page": 100, "_fields": "id,slug"}, timeout=60)
        for t in r.json():
            if re.match(r"^step-\d+$", t["slug"]):
                ids[t["id"]] = int(t["slug"].split("-")[1])
    except Exception as e:
        print("Tag list failed:", type(e).__name__)
    return ids


def apply(pid, cur_tags, steps, label):
    want = []
    for n in steps:
        t = tag_id(n)
        if t:
            want.append((n, t))
        elif DRY:
            want.append((n, None))      # در حالت آزمایشی برچسب هنوز ساخته نشده است
    new = [t for _, t in want if t and t not in cur_tags]
    missing = [n for n, t in want if t is None]
    txt = "step-" + ",".join(str(n) for n, _ in want)
    if not want:
        print("  [%s] %s: برچسبی مشخص نشد" % (pid, label)); return False
    if not new and not missing:
        print("  [%s] %s: قبلاً %s دارد" % (pid, label, txt)); return False
    print("  [%s] %s: %s %s" % (pid, label, "اضافه می‌شود" if not DRY else "اضافه خواهد شد (آزمایشی)", txt))
    if DRY:
        return True
    r = g.wp("POST", "%s/wp-json/wp/v2/posts/%s" % (g.WP, pid), tries=3, auth=g.AUTH, timeout=120, json={"tags": list(cur_tags) + new})
    ok = r.status_code in (200, 201)
    if not ok:
        print("    ✗ خطا %s: %s" % (r.status_code, r.text[:150]))
    return ok


def get_post(pid):
    r = g.wp("GET", "%s/wp-json/wp/v2/posts/%s" % (g.WP, pid), tries=3, auth=g.AUTH, timeout=90,
             params={"context": "edit", "_fields": "id,status,title,tags"})
    return r.json() if r.status_code == 200 else None


def mode_calendar():
    steps_map = g.load_steps()
    with open("calendar.csv", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    done = skipped = 0
    for r in rows:
        wid = (r.get("wp_id") or "").strip()
        st = g.parse_steps((r.get("steps") or "").strip() or steps_map.get(str(r["id"]).strip(), ""))
        if not st:
            continue
        if not wid:
            if r["status"].strip().lower() in ("published", "draft"):
                print("  [ردیف %s] %s: wp_id ندارد؛ دستی برچسب بزنید: step-%s" % (r["id"], r["topic"][:40], ",".join(map(str, st))))
                skipped += 1
            continue
        p = get_post(wid)
        if not p:
            print("  [%s] پیدا نشد" % wid); skipped += 1; continue
        if apply(wid, p.get("tags") or [], st, r["topic"][:40]):
            done += 1
    return done, skipped


def classify(title, excerpt):
    listing = "\n".join("%d) %s" % (k, v) for k, v in STEPS.items())
    try:
        out = g.ask("فهرست گام‌های مدل ۱۷ مرحله‌ای رشد کسب‌وکار:\n%s\n\nمقاله: «%s»\nخلاصه: %s\n\n"
                    "این مقاله بیشتر به کدام یک یا دو گام مربوط است؟ فقط به این شکل جواب بده:\nSTEPS: 7, 8" % (listing, title, excerpt[:500]),
                    40, "You classify business articles into a given list of steps. Answer only in the requested format.", 3)
    except SystemExit:
        return []
    m = re.search(r"STEPS:\s*([\d,\s|]+)", out)
    return g.parse_steps(m.group(1))[:2] if m else []


def mode_ai():
    known = step_tag_set()
    cal_ids = set()
    try:
        with open("calendar.csv", encoding="utf-8-sig", newline="") as f:
            cal_ids = {(r.get("wp_id") or "").strip() for r in csv.DictReader(f)}
    except FileNotFoundError:
        pass
    done, seen, page = 0, 0, 1
    while seen < LIMIT:
        r = g.wp("GET", g.WP + "/wp-json/wp/v2/posts", tries=3, auth=g.AUTH, timeout=90,
                 params={"status": "publish", "per_page": 50, "page": page, "context": "edit", "_fields": "id,title,excerpt,tags"})
        if r.status_code != 200 or not r.json():
            break
        for p in r.json():
            if seen >= LIMIT:
                break
            if str(p["id"]) in cal_ids or any(t in known for t in (p.get("tags") or [])):
                continue
            seen += 1
            title = g.plain((p.get("title") or {}).get("raw") or "", 200)
            exc = g.plain((p.get("excerpt") or {}).get("raw") or (p.get("excerpt") or {}).get("rendered") or "", 600)
            st = classify(title, exc)
            if apply(p["id"], p.get("tags") or [], st, title[:40]):
                done += 1
        page += 1
    return done, 0


if __name__ == "__main__":
    print("MODE=%s | DRY_RUN=%s" % (MODE, "بله (فقط گزارش)" if DRY else "خیر (اعمال)"))
    done, skipped = mode_ai() if MODE == "ai" else mode_calendar()
    print("پایان: %d مقاله %s، %d مورد نیازمند اقدام دستی." % (done, "قابل برچسب‌گذاری" if DRY else "برچسب خورد", skipped))
    if not DRY:
        g.notify("🏷️ برچسب‌گذاری گام‌های مدل انجام شد: %d مقاله (حالت %s)." % (done, MODE))
