"""
ارسال هفتگی PDF نشریه: شنبه ساعت ۱۰ صبح (وقت تهران) به کانال‌های تلگرام، بله و ایتا، با توضیح، امضا و آیدی کانال.
اجرا از ۹:۳۰ شروع می‌شود و دقیقاً تا ۱۰:۰۰ صبر می‌کند (چون زمان‌بندی GitHub گاهی دیر اجرا می‌شود).
TEST_OWNER=1  -> فقط به چت شخصی شما می‌فرستد (آزمایش) و علامت «ارسال‌شده» نمی‌زند.
"""
import os, sys, re, time
from datetime import datetime
from zoneinfo import ZoneInfo
import generate as g
import announce as a

API = g.WP + "/wp-json/mm-magazine/v1"
MAG_URL = os.environ.get("MAGAZINE_PAGE_URL", "https://mohammadmohajer.ir/business-growth-magazine/")
ISSUE_NO = os.environ.get("ISSUE_NO", "").strip()
TEST_OWNER = os.environ.get("TEST_OWNER", "0").strip().lower() in ("1", "true", "yes")
FORCE = os.environ.get("FORCE", "0").strip().lower() in ("1", "true", "yes")


def wait_until_ten():
    tz = ZoneInfo("Asia/Tehran")
    now = datetime.now(tz)
    target = now.replace(hour=10, minute=0, second=0, microsecond=0)
    if now >= target:
        print("Already past 10:00 Tehran; sending now.")
        return
    delta = (target - now).total_seconds()
    if delta > 55 * 60:
        print("More than 55 minutes to 10:00 (%.0f min); sending now." % (delta / 60))
        return
    print("Waiting %.0f seconds until 10:00 Tehran..." % delta)
    time.sleep(delta)


def pick_issue():
    r = g.wp("GET", API + "/issues", tries=3, timeout=90)
    if r.status_code != 200:
        sys.exit("فهرست شماره‌ها در دسترس نیست (HTTP %s)." % r.status_code)
    items = r.json().get("issues", [])
    if ISSUE_NO:
        sel = [i for i in items if str(i["no"]) == ISSUE_NO]
    else:
        sel = [i for i in items if (not i["open"]) and i.get("pdf") and not i.get("sent")]
    if not sel:
        return None
    return max(sel, key=lambda i: i["no"])


def titles_of(ids):
    url = "%s/wp-json/wp/v2/posts?include=%s&per_page=20&orderby=include&_fields=id,title" % (g.WP, ",".join(str(i) for i in ids))
    r = g.wp("GET", url, tries=3, timeout=90)
    out = []
    if r.status_code == 200:
        for p in r.json():
            out.append(g.plain((p.get("title") or {}).get("rendered", ""), 200))
    return out


def build_caption(issue, titles):
    no = issue["no"]
    link = "%s?issue=%s" % (MAG_URL, no)
    sp = "✍️ %s\n\n🆔️ %s" % (a.SIG_NAME, a.HANDLE)
    sh = "✍️ <b>%s</b>\n\n🆔️ %s" % (g.esc(a.SIG_NAME), g.esc(a.HANDLE))
    head_p = "📘 نشریه‌ی هفتگی رشد کسب‌وکار | شماره‌ی %s\n🗓 %s" % (g.fa(no), issue["range"])
    head_h = "<b>📘 نشریه‌ی هفتگی رشد کسب‌وکار | شماره‌ی %s</b>\n🗓 %s" % (g.fa(no), g.esc(issue["range"]))
    tail_p = ("\n\n📥 دانلود PDF و مطالعه‌ی آنلاین:\n%s\n\nاین نشریه را برای کسی که لازمش دارد بفرستید و شماره‌ی بعد را هر شنبه از دست ندهید.\n\n%s" % (link, sp))
    tail_h = ("\n\n📥 دانلود PDF و مطالعه‌ی آنلاین:\n%s\n\nاین نشریه را برای کسی که لازمش دارد بفرستید و شماره‌ی بعد را هر شنبه از دست ندهید.\n\n%s" % (g.esc(link), sh))
    lines_p, lines_h = [], []
    for i, t in enumerate(titles[:7]):
        t = t if len(t) <= 80 else t[:78].rsplit(" ", 1)[0] + "…"
        lines_p.append("%s) %s" % (g.fa(i + 1), t))
        lines_h.append("%s) %s" % (g.fa(i + 1), g.esc(t)))
        # کپشن تلگرام حداکثر ۱۰۲۴ نویسه است
        if len(head_h + "\n\nدر این شماره:\n" + "\n".join(lines_h) + tail_h) > 960:
            lines_p.pop()
            lines_h.pop()
            break
    body_p = ("\n\nدر این شماره:\n" + "\n".join(lines_p)) if lines_p else ""
    body_h = ("\n\nدر این شماره:\n" + "\n".join(lines_h)) if lines_h else ""
    return head_p + body_p + tail_p, head_h + body_h + tail_h, link


def main():
    issue = pick_issue()
    if not issue:
        print("شماره‌ی بسته‌شده‌ی دارای PDF که هنوز ارسال نشده باشد وجود ندارد.")
        if not TEST_OWNER:
            g.notify("ℹ️ ارسال هفتگی نشریه: شماره‌ی آماده‌ی ارسال پیدا نشد (PDF ساخته نشده یا قبلاً ارسال شده).")
        return
    no = issue["no"]
    print("Issue to send:", no, issue["range"])
    pdf_url = issue.get("pdf_url", "")
    if not pdf_url:
        sys.exit("آدرس PDF شماره‌ی %s ثبت نشده است." % no)
    data = g.S.get(pdf_url, timeout=180).content
    if data[:4] != b"%PDF":
        sys.exit("فایل PDF معتبر نیست.")
    titles = titles_of(issue["ids"])
    plain, html, link = build_caption(issue, titles)
    print("Caption length:", len(plain), len(html))

    if not TEST_OWNER:
        wait_until_ten()
    fname = "نشریه-رشد-کسب-وکار-شماره-%02d.pdf" % int(no)
    res = a.send_doc_all(data, fname, plain, html, link, "نشریه‌ی هفتگی رشد کسب‌وکار — شماره‌ی %s" % g.fa(no),
                         owner=TEST_OWNER, btn="مطالعه‌ی نشریه")
    line = " | ".join("%s %s" % (k, "✅" if v else "❌") for k, v in res.items()) or "هیچ مقصدی تنظیم نیست"
    print("Result:", line)
    if TEST_OWNER:
        g.notify("🧪 آزمایش ارسال هفتگی شماره‌ی %s (فقط به شما):\n%s" % (g.fa(no), line))
        return
    if any(res.values()):
        mr = g.wp("POST", API + "/asset", tries=3, auth=g.AUTH, timeout=90, json={"no": no, "sent": 1})
        print("Mark sent: HTTP", mr.status_code)
    g.notify("📘 PDF شماره‌ی %s نشریه در کانال‌ها ارسال شد:\n%s\n\n(ایمیل اعضا: هنوز به سامانه‌ی ایمیل وصل نشده است)" % (g.fa(no), line))


main()
